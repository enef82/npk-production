"""Часы ремонта оборудования → разноска табеля (`repToTimesheet` прототипа, реакция на
`equipment.repair_closed`, спецификация §3.5).

Часы ложатся строкой «Я / ремонт и ТО» на дату ремонта, вытесняя в тот же день сначала
накладные и простой, затем прочие разносимые строки — человек не работал 8 ч на
накладных и ещё 3 ч на ремонте. В закрытый для правки период часы не пишутся:
начальник производства получает уведомление и разносит их после переоткрытия.

Идемпотентно по (номер ремонта, сотрудник): повторная доставка события ничего не
меняет; последняя линия защиты от гонки — `timesheet_alloc_repair_unique`.
Не пользовательское действие — без `actor_context` (прецедент ИС
`production.services.order.create_order_from_inquiry`).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction

from src.core.accounts import facade as accounts
from src.core.notifications import facade as notifications
from src.core.org.models import Employee
from src.timesheet.calculations import (
    PRESENCE_CODE,
    DisplaceableRow,
    month_start,
    plan_repair_displacement,
)
from src.timesheet.models import (
    AllocationSource,
    AllocationTarget,
    TimeCode,
    WorkAllocation,
)
from src.timesheet.services.period import EDITABLE_STATUSES, lock_period

NOTIFICATION_CODE = "timesheet.repair_hours_locked"
# Получатель — держатель «правки любого подразделения»: по матрице прав (§4) это
# начальник производства, и адресат меняется сменой роли, а не кода.
NOTIFY_PERMISSION = "timesheet.edit_any"


@dataclass(frozen=True)
class RepairWorkerHours:
    employee_id: UUID
    hours: Decimal


@dataclass(frozen=True)
class RepairApplyResult:
    applied: int
    skipped: int  # уже разнесено ранее
    locked_employee_ids: list[UUID]


def _apply_one(employee_id: UUID, day: date, hours: Decimal, number: str, code: TimeCode) -> None:
    rows = list(
        WorkAllocation.objects.select_for_update()
        .filter(employee_id=employee_id, date=day, time_code__is_allocatable=True)
        .exclude(target=AllocationTarget.REPAIR)
        .order_by("created_at", "id")
    )
    plan = plan_repair_displacement([DisplaceableRow(r.id, r.target, r.hours) for r in rows], hours)
    for row in rows:
        if row.id not in plan:
            continue
        new_hours = plan[row.id]
        if new_hours <= 0:
            row.delete()
        else:
            row.hours = new_hours
            row.save(update_fields=["hours", "updated_at"])
    WorkAllocation.objects.create(
        employee_id=employee_id,
        date=day,
        time_code=code,
        target=AllocationTarget.REPAIR,
        hours=hours,
        source=AllocationSource.REPAIR,
        source_ref=number,
    )


def apply_repair_hours(
    number: str, day: date, workers: Sequence[RepairWorkerHours]
) -> RepairApplyResult:
    applied = skipped = 0
    locked: list[UUID] = []
    with transaction.atomic():
        code = TimeCode.objects.get(code=PRESENCE_CODE)
        employees = {
            e.id: e for e in Employee.objects.filter(id__in=[w.employee_id for w in workers])
        }
        for worker in workers:
            employee = employees.get(worker.employee_id)
            if employee is None or worker.hours <= 0:
                continue
            already = WorkAllocation.objects.filter(
                employee_id=employee.id, source=AllocationSource.REPAIR, source_ref=number
            ).exists()
            if already:
                skipped += 1
                continue
            period = lock_period(employee.department_id, month_start(day))
            if period.status not in EDITABLE_STATUSES:
                locked.append(employee.id)
                continue
            _apply_one(employee.id, day, worker.hours, number, code)
            applied += 1

        if locked:
            recipients = accounts.list_user_ids_with_perm(NOTIFY_PERMISSION)
            notifications.notify(
                recipients,
                NOTIFICATION_CODE,
                {
                    "number": number,
                    "date": day.strftime("%d.%m.%Y"),
                    "employees": ", ".join(employees[e].full_name for e in locked),
                    "employee_ids": [str(e) for e in locked],
                },
            )
    return RepairApplyResult(applied=applied, skipped=skipped, locked_employee_ids=locked)
