"""Заявка: создание с заказчиком из ядра, правка, этапы с визами, запуск в производство,
проигрыш (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.2).

Права проверяются в API. Сервис получает решение API флагом `may_approve` — «вправе
поставить визу текущего этапа»: если визы нет, а переводит ответственный, виза ставится
вместе с переходом (правило прототипа `moveTo`/`visaDialog`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.audit.context import actor_context
from src.core.common.scheduling import next_working_day
from src.core.events.publisher import publish
from src.core.identity import facade as identity
from src.core.numbering import facade as numbering
from src.core.org import facade as org
from src.core.org.models import Employee
from src.production import facade as production
from src.sales.calculations import calc_totals
from src.sales.events import InquiryLaunched
from src.sales.exceptions import (
    AlreadyApproved,
    CustomerNotFound,
    CustomerRequired,
    EmployeeNotFound,
    InvalidValues,
    LossReasonNotFound,
    ReasonRequired,
    StageRequirementsNotMet,
    StageSkip,
    TemplateNotFound,
    VisaRequired,
    invalid_transition_as,
)
from src.sales.models import (
    INQUIRY_STAGE_SEQUENCE,
    CalcMaterial,
    CalcOperation,
    CalcOperationDependency,
    Inquiry,
    InquiryStage,
    InquiryStageApproval,
    LossReason,
    SalesSettings,
)
from src.sales.planning import centers_by_id
from src.sales.selectors import lines_for_totals
from src.sales.services.calculation import has_plan, lock_inquiry

NUMERATOR_CODE = "sales.inquiry"

_FORWARD = {InquiryStage.NEW: "to_calc", InquiryStage.CALC: "to_approval"}
_BACKWARD = {InquiryStage.CALC: "back_to_new", InquiryStage.APPROVAL: "back_to_calc"}


@dataclass(frozen=True)
class NewCustomer:
    short_name: str
    inn: str = ""


@dataclass(frozen=True)
class InquiryCreateDTO:
    object_name: str
    quantity: Decimal
    due_date: date
    manager_id: UUID
    customer_id: UUID | None = None
    new_customer: NewCustomer | None = None
    template_id: UUID | None = None
    product_name: str = ""


@dataclass(frozen=True)
class InquiryUpdateDTO:
    object_name: str
    product_name: str
    template_id: UUID | None
    quantity: Decimal
    due_date: date
    manager_id: UUID
    overhead_pct: Decimal
    margin_pct: Decimal
    vat_pct: Decimal


@dataclass(frozen=True)
class LaunchResult:
    order_id: UUID
    warnings: list[str]


def get_settings() -> SalesSettings:
    settings, _ = SalesSettings.objects.get_or_create()
    return settings


def _get_employee(employee_id: UUID) -> Employee | None:
    return Employee.objects.filter(id=employee_id).first()


def _ensure_employee(employee_id: UUID) -> None:
    if employee_id not in {brief.id for brief in org.list_active_employees()}:
        raise EmployeeNotFound


def _ensure_template(template_id: UUID | None) -> str:
    if template_id is None:
        return ""
    template = production.get_template(template_id)
    if template is None:
        raise TemplateNotFound
    return template.name


def _resolve_customer(data: InquiryCreateDTO, actor_id: UUID) -> tuple[UUID, str]:
    if data.customer_id is not None:
        party = identity.get_party(data.customer_id)
        if party is None:
            raise CustomerNotFound
        return party.id, party.short_name
    if data.new_customer is None or not data.new_customer.short_name.strip():
        raise CustomerRequired
    name = data.new_customer.short_name.strip()
    # Дедупликация — в `create_party` (И5): похожий контрагент → 409 с кандидатами.
    party = identity.create_party(
        identity.PartyCreateDTO(
            inn=data.new_customer.inn.strip(), legal_name=name, short_name=name
        ),
        actor_id=actor_id,
    )
    return party.id, party.short_name


def _validate_quantity(quantity: Decimal) -> None:
    if quantity <= 0:
        raise InvalidValues("Количество должно быть больше нуля.")


def create_inquiry(data: InquiryCreateDTO, *, actor_id: UUID) -> UUID:
    _validate_quantity(data.quantity)
    _ensure_employee(data.manager_id)
    template_name = _ensure_template(data.template_id)
    with transaction.atomic(), actor_context(actor_id):
        customer_id, customer_name = _resolve_customer(data, actor_id)
        inquiry = Inquiry.objects.create(
            number=numbering.issue_number(NUMERATOR_CODE),
            customer_id=customer_id,
            customer_name=customer_name,
            object_name=data.object_name.strip(),
            template_id=data.template_id,
            product_name=data.product_name.strip() or template_name,
            quantity=data.quantity,
            due_date=data.due_date,
            manager_id=data.manager_id,
        )
        economist_id = get_settings().economist_id
        InquiryStageApproval.objects.bulk_create(
            [
                InquiryStageApproval(
                    inquiry=inquiry, stage=InquiryStage.NEW, responsible_id=data.manager_id
                ),
                InquiryStageApproval(
                    inquiry=inquiry, stage=InquiryStage.CALC, responsible_id=economist_id
                ),
                InquiryStageApproval(
                    inquiry=inquiry, stage=InquiryStage.APPROVAL, responsible_id=data.manager_id
                ),
            ]
        )
    return inquiry.id


def update_inquiry(inquiry_id: UUID, data: InquiryUpdateDTO, *, actor_id: UUID) -> None:
    """Реквизиты и проценты калькуляции. Менеджер — ответственный за этапы «Новые» и
    «Согласование КП»: при смене менеджера меняется и там, где виза ещё не стоит."""

    _validate_quantity(data.quantity)
    _ensure_employee(data.manager_id)
    _ensure_template(data.template_id)
    if data.overhead_pct < 0 or data.margin_pct < 0 or not 0 <= data.vat_pct <= 100:
        raise InvalidValues("Проценты калькуляции не могут быть отрицательными.")
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        if inquiry.manager_id != data.manager_id:
            InquiryStageApproval.objects.filter(
                inquiry=inquiry,
                stage__in=[InquiryStage.NEW, InquiryStage.APPROVAL],
                approved_at__isnull=True,
            ).update(responsible_id=data.manager_id)
        inquiry.object_name = data.object_name.strip()
        inquiry.product_name = data.product_name.strip()
        inquiry.template_id = data.template_id
        inquiry.quantity = data.quantity
        inquiry.due_date = data.due_date
        inquiry.manager_id = data.manager_id
        inquiry.overhead_pct = data.overhead_pct
        inquiry.margin_pct = data.margin_pct
        inquiry.vat_pct = data.vat_pct
        inquiry.save()


def _stage_label(stage: str) -> str:
    return str(InquiryStage(stage).label)


def _approve(approval: InquiryStageApproval, approver_id: UUID, comment: str) -> None:
    approval.approved_by_id = approver_id
    approval.approved_at = timezone.now()
    approval.comment = comment
    approval.save(update_fields=["approved_by", "approved_at", "comment", "updated_at"])


def _visa_required(approval: InquiryStageApproval) -> VisaRequired:
    responsible = _get_employee(approval.responsible_id) if approval.responsible_id else None
    return VisaRequired(
        f"Этап «{_stage_label(approval.stage)}» не завизирован. Перевести дальше можно после"
        f" визы ответственного{': ' + responsible.full_name if responsible else ''}."
    )


def approve_inquiry_stage(
    inquiry_id: UUID, stage: InquiryStage, *, actor_id: UUID, approver_id: UUID, comment: str = ""
) -> None:
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        if inquiry.stage != stage:
            raise StageRequirementsNotMet("Визируется только текущий этап заявки.")
        approval = InquiryStageApproval.objects.select_for_update().get(
            inquiry=inquiry, stage=stage
        )
        if approval.approved_at is not None:
            raise AlreadyApproved
        _approve(approval, approver_id, comment.strip())


def move_inquiry_stage(
    inquiry_id: UUID,
    to: InquiryStage,
    *,
    actor_id: UUID,
    actor_employee_id: UUID | None,
    comment: str = "",
    may_approve: bool = False,
) -> None:
    """`checkMove` прототипа (§3.2): по порядку; назад на один с причиной (виза целевого
    этапа снимается); `calc → approval` — есть калькуляция и план; вперёд — после визы
    текущего этапа. Запуск и проигрыш — отдельные действия."""

    comment = comment.strip()
    if to not in INQUIRY_STAGE_SEQUENCE:
        raise StageSkip("Запуск и проигрыш — отдельные действия.")
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        current = InquiryStage(inquiry.stage)
        distance = INQUIRY_STAGE_SEQUENCE.index(to) - INQUIRY_STAGE_SEQUENCE.index(current)
        if distance == 0:
            raise StageSkip("Заявка уже на этом этапе.")
        if abs(distance) > 1:
            raise StageSkip(
                "Вернуть можно только на один этап назад."
                if distance < 0
                else "Этапы проходятся по порядку — перескочить нельзя."
            )
        if distance < 0:
            if not comment:
                raise ReasonRequired("Укажите причину возврата.")
            with invalid_transition_as():
                getattr(inquiry, _BACKWARD[current])()
            inquiry.save(update_fields=["stage", "updated_at"])
            InquiryStageApproval.objects.filter(inquiry=inquiry, stage=to).update(
                approved_by=None, approved_at=None, comment=""
            )
            return
        if to == InquiryStage.APPROVAL:
            has_calc = (
                CalcMaterial.objects.filter(inquiry=inquiry).exists()
                or CalcOperation.objects.filter(inquiry=inquiry).exists()
            )
            if not has_calc:
                raise StageRequirementsNotMet("Нет калькуляции — сначала посчитайте заказ.")
            if not has_plan(inquiry):
                raise StageRequirementsNotMet(
                    "Нет плана реализации — сформируйте план в карточке (вкладка «План»)."
                )
        _approve_current_or_fail(inquiry, current, actor_employee_id, comment, may_approve)
        with invalid_transition_as():
            getattr(inquiry, _FORWARD[current])()
        inquiry.save(update_fields=["stage", "updated_at"])


def _approve_current_or_fail(
    inquiry: Inquiry,
    current: InquiryStage,
    actor_employee_id: UUID | None,
    comment: str,
    may_approve: bool,
) -> None:
    approval = InquiryStageApproval.objects.select_for_update().get(inquiry=inquiry, stage=current)
    if approval.approved_at is not None:
        return
    if not may_approve or actor_employee_id is None:
        raise _visa_required(approval)
    _approve(approval, actor_employee_id, comment)


def set_inquiry_stage_responsible(
    inquiry_id: UUID, stage: InquiryStage, responsible_id: UUID, *, actor_id: UUID
) -> None:
    _ensure_employee(responsible_id)
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        InquiryStageApproval.objects.filter(inquiry=inquiry, stage=stage).update(
            responsible_id=responsible_id, updated_at=timezone.now()
        )


def launch_inquiry(
    inquiry_id: UUID,
    *,
    planned_start: date,
    due_date: date,
    actor_id: UUID,
    actor_employee_id: UUID | None,
    may_approve: bool = False,
) -> LaunchResult:
    """«Запуск в работу» (§3.2): `approval → launched`. В одной транзакции —
    `production.facade.create_order_from_inquiry` (копия операций со связями и сумм
    калькуляции), `order_id`, этап и `sales.inquiry_launched` (И4). Без КД запуск
    не блокируется — возвращается предупреждение."""

    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        if inquiry.stage != InquiryStage.APPROVAL:
            raise StageRequirementsNotMet("Запустить можно заявку на этапе «Согласование КП».")
        operations = list(CalcOperation.objects.filter(inquiry=inquiry).order_by("seq"))
        if not operations:
            raise StageRequirementsNotMet("В калькуляции нет операций — запускать нечего.")
        _approve_current_or_fail(inquiry, InquiryStage.APPROVAL, actor_employee_id, "", may_approve)
        index = {op.id: i for i, op in enumerate(operations)}
        preds: dict[UUID, list[int]] = {op.id: [] for op in operations}
        for dep in CalcOperationDependency.objects.filter(successor__inquiry=inquiry):
            preds[dep.successor_id].append(index[dep.predecessor_id])
        materials, labor_lines = lines_for_totals(
            list(CalcMaterial.objects.filter(inquiry=inquiry)), operations, centers_by_id()
        )
        totals = calc_totals(
            materials,
            labor_lines,
            overhead_pct=inquiry.overhead_pct,
            margin_pct=inquiry.margin_pct,
            vat_pct=inquiry.vat_pct,
        )
        order_id = production.create_order_from_inquiry(
            production.LaunchData(
                inquiry_id=inquiry.id,
                inquiry_number=inquiry.number,
                customer_id=inquiry.customer_id,
                customer_name=inquiry.customer_name,
                object_name=inquiry.object_name,
                product_name=inquiry.product_name or inquiry.object_name or inquiry.number,
                template_id=inquiry.template_id,
                quantity=inquiry.quantity,
                manager_id=inquiry.manager_id,
                planned_start=next_working_day(planned_start),
                due_date=due_date,
                contract_total=totals.total,
                labor_cost_planned=totals.labor,
                operations=[
                    production.LaunchOperation(
                        seq=op.seq,
                        name=op.name,
                        work_center_id=op.work_center_id,
                        hours=op.hours,
                        people=op.people,
                        not_before=op.not_before,
                        predecessor_indexes=tuple(sorted(preds[op.id])),
                    )
                    for op in operations
                ],
            ),
            actor_id=actor_id,
        )
        with invalid_transition_as():
            inquiry.mark_launched()
        inquiry.order_id = order_id
        inquiry.due_date = due_date
        inquiry.save(update_fields=["stage", "order_id", "due_date", "updated_at"])
        publish(InquiryLaunched(aggregate_id=inquiry.id, order_id=order_id))
        warnings = []
        if not production.order_has_kd(order_id):
            warnings.append(
                "К заказу не приложена КД / чертежи. Этап «Подготовка производства» "
                "не закроется без документации."
            )
    return LaunchResult(order_id=order_id, warnings=warnings)


def lose_inquiry(inquiry_id: UUID, reason_id: UUID, comment: str, *, actor_id: UUID) -> None:
    reason = LossReason.objects.filter(id=reason_id, is_active=True).first()
    if reason is None:
        raise LossReasonNotFound
    with transaction.atomic(), actor_context(actor_id):
        inquiry = lock_inquiry(inquiry_id)
        with invalid_transition_as():
            inquiry.mark_lost()
        inquiry.lost_reason = reason
        inquiry.lost_comment = comment.strip()
        inquiry.save(update_fields=["stage", "lost_reason", "lost_comment", "updated_at"])
