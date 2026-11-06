"""Эндпоинты django-ninja модуля «Оборудование и ТО» — экран «Оборудование»
(§3.6, §6; прототип `renderMachines`, `machDialog`, `repairsPanel`, `repDialog`).

Права проверяются здесь, сервисы их не проверяют (как в `production` ИС). Карточки
отдают серверные `abilities` — фронт показывает действия по ним. Чтение — любой
аутентифицированный.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Protocol
from uuid import UUID

from django.http import Http404, HttpRequest
from django.utils import timezone
from ninja import Query, Router

from src.core.common.exceptions import PermissionDenied
from src.equipment import selectors
from src.equipment.calculations import WeekSummary, week_start
from src.equipment.models import (
    DownReason,
    Equipment,
    EquipmentStatus,
    MaintenanceType,
    Repair,
    RepairKind,
    RepairStatus,
    RuntimeLog,
    RuntimeSource,
)
from src.equipment.rules import can_log_runtime, can_manage_equipment
from src.equipment.services import equipment as equipment_services
from src.equipment.services import repair as repair_services
from src.equipment.services import runtime as runtime_services

from .filters import RepairFilters
from .schemas import (
    CategoryDowntimeOut,
    DashboardAbilitiesOut,
    DashboardOut,
    DownReasonOut,
    EquipmentAbilitiesOut,
    EquipmentFailuresOut,
    EquipmentIn,
    EquipmentListItem,
    EquipmentOut,
    KpiOut,
    MaintenancePlanOut,
    MaintenanceStateOut,
    MaintenanceTypeIn,
    MatrixRowOut,
    ParetoOut,
    PerformMaintenanceIn,
    ReferenceItemOut,
    ReferenceOut,
    RepairAbilitiesOut,
    RepairCloseIn,
    RepairCreateIn,
    RepairIn,
    RepairJournalOut,
    RepairListItem,
    RepairOut,
    RepairsSummaryOut,
    RuntimeIn,
    RuntimeOut,
    StatusIn,
    WeekOut,
    WorkerOut,
)

router = Router(tags=["equipment"])

WEEKS_SHOWN = 8
RECENT_RUNTIME = 7
RECENT_REPAIRS = 8
MAINTENANCE_HORIZON_DAYS = 30


class _AuthenticatedUser(Protocol):
    id: UUID
    is_superuser: bool

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


class AuthenticatedHttpRequest(HttpRequest):
    auth: _AuthenticatedUser


def _require_manage(user: _AuthenticatedUser) -> None:
    if not can_manage_equipment(user):
        raise PermissionDenied("Оборудование и ТО ведёт начальник производства.")


def _require_log(user: _AuthenticatedUser) -> None:
    if not can_log_runtime(user):
        raise PermissionDenied(
            "Наработку и ремонты вносят мастер участка и начальник производства."
        )


# --- Преобразования ---------------------------------------------------------------


def _week_out(monday: date, summary: WeekSummary) -> WeekOut:
    return WeekOut(
        week_start=monday,
        run=summary.run,
        setup=summary.setup,
        idle=summary.idle,
        down=summary.down,
        days=summary.days,
        utilization=summary.utilization,
    )


def _maintenance_out(row: selectors.MaintenanceRow) -> MaintenanceStateOut:
    mtype = row.maintenance_type
    return MaintenanceStateOut(
        maintenance_type_id=mtype.id,
        code=mtype.code,
        interval_hours=mtype.interval_hours,
        scope=mtype.scope,
        last_date=row.last_date,
        last_at_hours=row.last_at_hours,
        next_at_hours=row.forecast.next_at_hours,
        hours_left=row.forecast.hours_left,
        due_date=row.forecast.due_date,
        state=row.forecast.state,
    )


def _runtime_out(log: RuntimeLog) -> RuntimeOut:
    return RuntimeOut(
        id=log.id,
        date=log.date,
        run=log.run,
        setup=log.setup,
        idle=log.idle,
        down=log.down,
        idle_reason_id=log.idle_reason_id,
        idle_reason_name=log.idle_reason.name if log.idle_reason else "",
        down_reason_id=log.down_reason_id,
        down_reason_name=log.down_reason.name if log.down_reason else "",
        source=RuntimeSource(log.source),
    )


def _repair_item(repair: Repair) -> RepairListItem:
    return RepairListItem(
        id=repair.id,
        number=repair.number,
        equipment_id=repair.equipment_id,
        equipment_name=repair.equipment.name,
        equipment_inventory_no=repair.equipment.inventory_no,
        kind=RepairKind(repair.kind),
        maintenance_type_id=repair.maintenance_type_id,
        category_id=repair.category_id,
        category_name=repair.category.name if repair.category else "",
        started_at=repair.started_at,
        finished_at=repair.finished_at,
        downtime_hours=selectors.repair_downtime(repair),
        labor_hours=selectors.repair_labor(repair),
        description=repair.description,
        fix=repair.fix,
        status=RepairStatus(repair.status),
    )


def _equipment_abilities(user: _AuthenticatedUser) -> EquipmentAbilitiesOut:
    manage = bool(can_manage_equipment(user))
    log = bool(can_log_runtime(user))
    return EquipmentAbilitiesOut(
        can_edit=manage,
        can_set_status=log,
        can_log_runtime=log,
        can_register_repair=log,
        can_manage_maintenance=manage,
    )


def _repair_abilities(user: _AuthenticatedUser, repair: Repair) -> RepairAbilitiesOut:
    log = bool(can_log_runtime(user))
    is_open = repair.status != RepairStatus.DONE
    return RepairAbilitiesOut(
        can_edit=log and is_open,
        can_start=log and repair.status == RepairStatus.OPEN,
        can_close=log and is_open,
    )


def _repair_out(user: _AuthenticatedUser, repair_id: UUID) -> RepairOut:
    repair = selectors.get_repair(repair_id)
    if repair is None:
        raise Http404
    return RepairOut(
        **_repair_item(repair).model_dump(),
        alarm_code=repair.alarm_code,
        parts=repair.parts,
        maintenance_type_code=repair.maintenance_type.code if repair.maintenance_type else "",
        workers=[
            WorkerOut(
                employee_id=worker.employee_id,
                employee_name=worker.employee.full_name,
                hours=worker.hours,
            )
            for worker in repair.workers.all()
        ],
        created_at=repair.created_at,
        abilities=_repair_abilities(user, repair),
    )


def _equipment_out(user: _AuthenticatedUser, equipment_id: UUID) -> EquipmentOut:
    equipment = selectors.get_equipment(equipment_id)
    if equipment is None:
        raise Http404
    today = timezone.localdate()
    current = week_start(today)
    weeks = [current - timedelta(weeks=WEEKS_SHOWN - 1 - i) for i in range(WEEKS_SHOWN)]
    summaries = selectors.week_summaries([equipment.id], weeks)[equipment.id]
    maintenance = selectors.maintenance_by_equipment([equipment], today).get(equipment.id, [])
    return EquipmentOut(
        id=equipment.id,
        inventory_no=equipment.inventory_no,
        name=equipment.name,
        work_center_id=equipment.work_center_id,
        control_system=equipment.control_system,
        connection=equipment.connection,
        status=EquipmentStatus(equipment.status),
        operating_hours_initial=equipment.operating_hours_initial,
        operating_hours=selectors.operating_hours(equipment),
        weeks=[_week_out(week, summaries[week]) for week in weeks],
        maintenance=[_maintenance_out(row) for row in maintenance],
        recent_runtime=[
            _runtime_out(log) for log in selectors.runtime_logs(equipment.id)[:RECENT_RUNTIME]
        ],
        recent_repairs=[
            _repair_item(repair)
            for repair in selectors.list_repairs(equipment_id=equipment.id)[:RECENT_REPAIRS]
        ],
        abilities=_equipment_abilities(user),
    )


def _existing(model: type[Equipment | MaintenanceType | Repair], object_id: UUID) -> None:
    if not model.objects.filter(id=object_id).exists():
        raise Http404


# --- Справочники и сводка ---------------------------------------------------------


@router.get("/reference", response=ReferenceOut, operation_id="getEquipmentReference")
def get_reference(request: HttpRequest) -> ReferenceOut:
    down: list[DownReason] = list(selectors.list_down_reasons())
    return ReferenceOut(
        idle_reasons=[
            ReferenceItemOut(id=r.id, name=r.name) for r in selectors.list_idle_reasons()
        ],
        down_reasons=[
            DownReasonOut(
                id=r.id,
                name=r.name,
                repair_kind=RepairKind(r.repair_kind) if r.repair_kind else None,
            )
            for r in down
        ],
        failure_categories=[
            ReferenceItemOut(id=c.id, name=c.name) for c in selectors.list_failure_categories()
        ],
    )


@router.get("/dashboard", response=DashboardOut, operation_id="getEquipmentDashboard")
def get_dashboard(request: AuthenticatedHttpRequest, week: date | None = None) -> DashboardOut:
    """Сводка экрана: KPI недели, матрица загрузки 8 недель, Парето простоев, план ТО.
    Недели — 8 полных до текущей (как в прототипе); `week` — любая дата недели."""

    today = timezone.localdate()
    current = week_start(today)
    weeks = [current - timedelta(weeks=WEEKS_SHOWN - i) for i in range(WEEKS_SHOWN)]
    selected = week_start(week) if week is not None else weeks[-1]
    shown = sorted({*weeks, selected})
    equipment = list(selectors.list_equipment())
    ids = [item.id for item in equipment]
    summaries = selectors.week_summaries(ids, shown)
    states = selectors.maintenance_by_equipment(equipment, today)
    kpi = selectors.dashboard_kpi(
        equipment, {eid: by_week[selected] for eid, by_week in summaries.items()}, states
    )
    plan = selectors.maintenance_plan(today, MAINTENANCE_HORIZON_DAYS)
    return DashboardOut(
        week_start=selected,
        weeks=weeks,
        kpi=KpiOut(
            equipment_count=kpi.equipment_count,
            utilization=kpi.utilization,
            idle_and_down_hours=kpi.idle_and_down_hours,
            maintenance_overdue=kpi.maintenance_overdue,
            maintenance_soon=kpi.maintenance_soon,
        ),
        matrix=[
            MatrixRowOut(
                equipment_id=item.id,
                name=item.name,
                weeks=[_week_out(w, summaries[item.id][w]) for w in weeks],
            )
            for item in equipment
        ],
        pareto=[
            ParetoOut(reason=row.reason, is_down=row.is_down, hours=row.hours)
            for row in selectors.downtime_pareto(selected, selected + timedelta(days=6))
        ],
        maintenance_plan=[
            MaintenancePlanOut(
                equipment_id=entry.equipment.id,
                equipment_name=entry.equipment.name,
                maintenance=_maintenance_out(entry.row),
            )
            for entry in plan
        ],
        abilities=DashboardAbilitiesOut(
            can_create_equipment=bool(can_manage_equipment(request.auth)),
            can_register_repair=bool(can_log_runtime(request.auth)),
        ),
    )


# --- Оборудование -----------------------------------------------------------------


@router.get("/machines", response=list[EquipmentListItem], operation_id="listEquipment")
def list_machines(request: HttpRequest, week: date | None = None) -> list[EquipmentListItem]:
    """Таблица «Оборудование, наработка и ТО» за неделю (`week` — любая её дата;
    по умолчанию — прошлая полная неделя)."""

    today = timezone.localdate()
    selected = week_start(week) if week is not None else week_start(today) - timedelta(weeks=1)
    equipment = list(selectors.list_equipment())
    ids = [item.id for item in equipment]
    summaries = selectors.week_summaries(ids, [selected])
    states = selectors.maintenance_by_equipment(equipment, today)
    result = []
    for item in equipment:
        rows = states.get(item.id, [])
        result.append(
            EquipmentListItem(
                id=item.id,
                inventory_no=item.inventory_no,
                name=item.name,
                work_center_id=item.work_center_id,
                control_system=item.control_system,
                connection=item.connection,
                status=EquipmentStatus(item.status),
                operating_hours=selectors.operating_hours(item),
                week=_week_out(selected, summaries[item.id][selected]),
                nearest_maintenance=_maintenance_out(rows[0]) if rows else None,
            )
        )
    return result


@router.post("/machines", response=EquipmentOut, operation_id="createEquipment")
def create_machine(request: AuthenticatedHttpRequest, data: EquipmentIn) -> EquipmentOut:
    _require_manage(request.auth)
    equipment = equipment_services.create_equipment(
        equipment_services.EquipmentDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _equipment_out(request.auth, equipment.id)


@router.get("/machines/{equipment_id}", response=EquipmentOut, operation_id="getEquipment")
def get_machine(request: AuthenticatedHttpRequest, equipment_id: UUID) -> EquipmentOut:
    return _equipment_out(request.auth, equipment_id)


@router.patch("/machines/{equipment_id}", response=EquipmentOut, operation_id="updateEquipment")
def update_machine(
    request: AuthenticatedHttpRequest, equipment_id: UUID, data: EquipmentIn
) -> EquipmentOut:
    _require_manage(request.auth)
    _existing(Equipment, equipment_id)
    equipment_services.update_equipment(
        equipment_id, equipment_services.EquipmentDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _equipment_out(request.auth, equipment_id)


@router.post(
    "/machines/{equipment_id}/status", response=EquipmentOut, operation_id="setEquipmentStatus"
)
def set_machine_status(
    request: AuthenticatedHttpRequest, equipment_id: UUID, data: StatusIn
) -> EquipmentOut:
    _require_log(request.auth)
    _existing(Equipment, equipment_id)
    equipment_services.set_equipment_status(equipment_id, data.status, actor_id=request.auth.id)
    return _equipment_out(request.auth, equipment_id)


@router.get(
    "/machines/{equipment_id}/runtime", response=list[RuntimeOut], operation_id="listRuntime"
)
def list_runtime(
    request: HttpRequest,
    equipment_id: UUID,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[RuntimeOut]:
    _existing(Equipment, equipment_id)
    return [_runtime_out(log) for log in selectors.runtime_logs(equipment_id, date_from, date_to)]


@router.put("/machines/{equipment_id}/runtime", response=EquipmentOut, operation_id="recordRuntime")
def record_runtime(
    request: AuthenticatedHttpRequest, equipment_id: UUID, data: RuntimeIn
) -> EquipmentOut:
    """«Записать смену»: наработка за сутки, заменяет прежнюю запись тех же суток."""

    _require_log(request.auth)
    _existing(Equipment, equipment_id)
    runtime_services.record_runtime(
        equipment_id, runtime_services.RuntimeDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _equipment_out(request.auth, equipment_id)


# --- Виды ТО ----------------------------------------------------------------------


@router.post(
    "/machines/{equipment_id}/maintenance-types",
    response=EquipmentOut,
    operation_id="createMaintenanceType",
)
def create_maintenance_type(
    request: AuthenticatedHttpRequest, equipment_id: UUID, data: MaintenanceTypeIn
) -> EquipmentOut:
    _require_manage(request.auth)
    _existing(Equipment, equipment_id)
    equipment_services.create_maintenance_type(
        equipment_id,
        equipment_services.MaintenanceTypeDTO(**data.model_dump()),
        actor_id=request.auth.id,
    )
    return _equipment_out(request.auth, equipment_id)


@router.patch(
    "/maintenance-types/{maintenance_type_id}",
    response=EquipmentOut,
    operation_id="updateMaintenanceType",
)
def update_maintenance_type(
    request: AuthenticatedHttpRequest, maintenance_type_id: UUID, data: MaintenanceTypeIn
) -> EquipmentOut:
    _require_manage(request.auth)
    mtype = MaintenanceType.objects.filter(id=maintenance_type_id).first()
    if mtype is None:
        raise Http404
    equipment_services.update_maintenance_type(
        maintenance_type_id,
        equipment_services.MaintenanceTypeDTO(**data.model_dump()),
        actor_id=request.auth.id,
    )
    return _equipment_out(request.auth, mtype.equipment_id)


@router.post(
    "/maintenance-types/{maintenance_type_id}/perform",
    response=RepairOut,
    operation_id="performMaintenance",
)
def perform_maintenance(
    request: AuthenticatedHttpRequest, maintenance_type_id: UUID, data: PerformMaintenanceIn
) -> RepairOut:
    """«Провести» ТО: закрытая запись журнала вида «ТО» и отметка о проведённом ТО."""

    _require_log(request.auth)
    _existing(MaintenanceType, maintenance_type_id)
    repair = repair_services.perform_maintenance(
        maintenance_type_id,
        repair_services.MaintenanceDTO(
            started_at=data.started_at,
            finished_at=data.finished_at,
            workers=[
                repair_services.WorkerDTO(employee_id=w.employee_id, hours=w.hours)
                for w in data.workers
            ],
            comment=data.comment,
        ),
        actor_id=request.auth.id,
    )
    return _repair_out(request.auth, repair.id)


# --- Аварии и ремонты -------------------------------------------------------------


def _repair_dto(data: RepairIn) -> repair_services.RepairDTO:
    return repair_services.RepairDTO(
        kind=data.kind,
        started_at=data.started_at,
        finished_at=data.finished_at,
        description=data.description,
        maintenance_type_id=data.maintenance_type_id,
        category_id=data.category_id,
        alarm_code=data.alarm_code,
        fix=data.fix,
        parts=data.parts,
        workers=[
            repair_services.WorkerDTO(employee_id=w.employee_id, hours=w.hours)
            for w in data.workers
        ],
    )


@router.get("/repairs", response=RepairJournalOut, operation_id="listRepairs")
def list_repairs(
    request: AuthenticatedHttpRequest, filters: RepairFilters = Query(...)
) -> RepairJournalOut:
    """Журнал аварий и ремонтов за `days` дней (незакрытые — всегда) со сводкой:
    аварии, простой, трудозатраты, MTTR, MTBF, простой по категориям."""

    now = timezone.now()
    date_from = timezone.localdate() - timedelta(days=filters.days)
    repairs = list(
        selectors.list_repairs(
            date_from=date_from, kind=filters.kind, equipment_id=filters.equipment_id
        )
    )
    # Незакрытые — сверху, как в прототипе.
    repairs.sort(key=lambda r: r.status == RepairStatus.DONE)
    summary = selectors.summarize_repairs(
        repairs, date_from=date_from, equipment_id=filters.equipment_id, now=now
    )
    return RepairJournalOut(
        items=[_repair_item(repair) for repair in repairs],
        summary=RepairsSummaryOut(
            failures=summary.failures,
            failure_downtime=summary.failure_downtime,
            labor_hours=summary.labor_hours,
            mttr=summary.mttr,
            mtbf=summary.mtbf,
            downtime_by_category=[
                CategoryDowntimeOut(category=name, hours=hours)
                for name, hours in summary.downtime_by_category
            ],
            failures_by_equipment=[
                EquipmentFailuresOut(equipment_id=eid, equipment_name=name, failures=count)
                for eid, name, count in summary.failures_by_equipment
            ],
        ),
        can_register=bool(can_log_runtime(request.auth)),
    )


@router.post("/repairs", response=RepairOut, operation_id="createRepair")
def create_repair(request: AuthenticatedHttpRequest, data: RepairCreateIn) -> RepairOut:
    _require_log(request.auth)
    _existing(Equipment, data.equipment_id)
    repair = repair_services.create_repair(
        data.equipment_id, _repair_dto(data), actor_id=request.auth.id
    )
    return _repair_out(request.auth, repair.id)


@router.get("/repairs/{repair_id}", response=RepairOut, operation_id="getRepair")
def get_repair(request: AuthenticatedHttpRequest, repair_id: UUID) -> RepairOut:
    return _repair_out(request.auth, repair_id)


@router.patch("/repairs/{repair_id}", response=RepairOut, operation_id="updateRepair")
def update_repair(request: AuthenticatedHttpRequest, repair_id: UUID, data: RepairIn) -> RepairOut:
    _require_log(request.auth)
    _existing(Repair, repair_id)
    repair_services.update_repair(repair_id, _repair_dto(data), actor_id=request.auth.id)
    return _repair_out(request.auth, repair_id)


@router.post("/repairs/{repair_id}/start", response=RepairOut, operation_id="startRepair")
def start_repair(request: AuthenticatedHttpRequest, repair_id: UUID) -> RepairOut:
    _require_log(request.auth)
    _existing(Repair, repair_id)
    repair_services.start_repair(repair_id, actor_id=request.auth.id)
    return _repair_out(request.auth, repair_id)


@router.post("/repairs/{repair_id}/close", response=RepairOut, operation_id="closeRepair")
def close_repair(
    request: AuthenticatedHttpRequest, repair_id: UUID, data: RepairCloseIn
) -> RepairOut:
    """«Устранено — закрыть»: часы исполнителей уходят в табель событием."""

    _require_log(request.auth)
    _existing(Repair, repair_id)
    repair_services.close_repair(repair_id, finished_at=data.finished_at, actor_id=request.auth.id)
    return _repair_out(request.auth, repair_id)
