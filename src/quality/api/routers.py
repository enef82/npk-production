"""Эндпоинты django-ninja модуля «ОТК и качество» — блок контроля карточки операции и
экран «Качество» (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3, §6; прототип
`opDialog`, `renderQuality`).

Права проверяются здесь, сервисы их не проверяют. Блок операции отдаёт серверные
`abilities`, посчитанные той же функцией, что и проверка записи. Чтение — любой
аутентифицированный.
"""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.http import Http404, HttpRequest
from django.utils import timezone
from ninja import Query, Router
from ninja.responses import Status

from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied
from src.production import facade as production
from src.quality import rules, selectors
from src.quality.exceptions import ActorNotEmployee
from src.quality.models import DefectCause, InspectionPoint, InspectionRecord
from src.quality.services import inspection as inspection_services
from src.quality.services.inspection import RECORDING_STAGES, SUPPLY_RECORDING_STAGES

from .filters import RecordFilters, SummaryFilters
from .schemas import (
    DefectCauseOut,
    DefectTypeOut,
    InspectionCreatedOut,
    InspectionIn,
    InspectionPointOut,
    InspectionRecordOut,
    JournalRecordOut,
    OperationQcAbilitiesOut,
    OperationQcOut,
    QcAggOut,
    QualityKpiOut,
    QualityParetoOut,
    QualityReferenceOut,
    QualitySummaryOut,
    TopDefectOut,
    WeekQcOut,
    WorkCenterQcOut,
)

router = Router(tags=["quality"])

DYNAMICS_WEEKS = 12
REMAKE_WARNING = "Списано {scrap} шт. — нужно повторное изготовление; учтите в плане."


class AuthenticatedHttpRequest(HttpRequest):
    auth: User


# --- Преобразования ---------------------------------------------------------------


def _work_center_names() -> dict[UUID, str]:
    return {center.id: center.name for center in production.list_work_centers()}


def _point_out(point: InspectionPoint, names: dict[UUID, str]) -> InspectionPointOut:
    return InspectionPointOut(
        id=point.id,
        work_center_id=point.work_center_id,
        work_center_name=names.get(point.work_center_id, ""),
        name=point.name,
        is_final=point.is_final,
        defect_types=[
            DefectTypeOut(id=t.id, name=t.name) for t in point.defect_types.all() if t.is_active
        ],
    )


def _cause_out(cause: DefectCause) -> DefectCauseOut:
    return DefectCauseOut(id=cause.id, name=cause.name, is_operator_fault=cause.is_operator_fault)


def _record_out(record: InspectionRecord) -> InspectionRecordOut:
    return InspectionRecordOut(
        id=record.id,
        operation_id=record.operation_id,
        order_id=record.order_id,
        work_center_id=record.work_center_id,
        date=record.date,
        inspector_id=record.inspector_id,
        inspector_name=record.inspector.full_name,
        checked=record.checked,
        rework=record.rework,
        scrap=record.scrap,
        defect_type_id=record.defect_type_id,
        defect_type_name=record.defect_type.name if record.defect_type else "",
        cause_id=record.cause_id,
        cause_name=record.cause.name if record.cause else "",
        comment=record.comment,
        created_at=record.created_at,
    )


def _agg_out(totals: selectors.QcTotals) -> QcAggOut:
    return QcAggOut(
        checked=totals.checked,
        rework=totals.rework,
        scrap=totals.scrap,
        defects=totals.defects,
        pct=totals.pct,
    )


def _operation(operation_id: UUID) -> production.OperationBrief:
    operation = production.get_operations_brief([operation_id]).get(operation_id)
    if operation is None:
        raise Http404
    return operation


def _can_record(user: User, operation: production.OperationBrief) -> bool:
    return rules.can_record_for_operation(user, operation.responsible_id)


# --- Справочники ------------------------------------------------------------------


@router.get("/reference", response=QualityReferenceOut, operation_id="getQualityReference")
def get_reference(request: HttpRequest) -> QualityReferenceOut:
    names = _work_center_names()
    return QualityReferenceOut(
        points=[_point_out(point, names) for point in selectors.list_points()],
        causes=[_cause_out(cause) for cause in selectors.list_causes()],
    )


# --- Контроль операции ------------------------------------------------------------


def _operation_qc(user: User, operation_id: UUID) -> OperationQcOut:
    operation = _operation(operation_id)
    order = production.get_orders_brief([operation.order_id])[operation.order_id]
    point = selectors.get_point_for_work_center(operation.work_center_id)
    records = selectors.records_for_operation(operation.id)
    totals = selectors.qc_by_operation([operation.id]).get(operation.id, selectors.QcTotals())
    stages = SUPPLY_RECORDING_STAGES if operation.is_supply else RECORDING_STAGES
    recording_open = point is not None and order.stage in stages
    return OperationQcOut(
        operation_id=operation.id,
        order_id=operation.order_id,
        work_center_id=operation.work_center_id,
        point=_point_out(point, _work_center_names()) if point is not None else None,
        recording_open=recording_open,
        default_checked=max(1, int(order.quantity)),
        aggregate=_agg_out(totals),
        records=[_record_out(record) for record in records],
        causes=[_cause_out(cause) for cause in selectors.list_causes()],
        abilities=OperationQcAbilitiesOut(
            can_record=recording_open and _can_record(user, operation)
        ),
    )


@router.get(
    "/operations/{operation_id}",
    response=OperationQcOut,
    operation_id="getOperationQc",
)
def get_operation_qc(request: AuthenticatedHttpRequest, operation_id: UUID) -> OperationQcOut:
    return _operation_qc(request.auth, operation_id)


@router.post(
    "/operations/{operation_id}/records",
    response={201: InspectionCreatedOut},
    operation_id="recordInspection",
)
def record_inspection(
    request: AuthenticatedHttpRequest, operation_id: UUID, payload: InspectionIn
) -> Status[InspectionCreatedOut]:
    user = request.auth
    operation = _operation(operation_id)
    if not _can_record(user, operation):
        raise PermissionDenied(
            "Результат контроля записывают инженер ОТК, мастер участка и ответственный за операцию."
        )
    inspector_id = rules.employee_id_of(user)
    if inspector_id is None:
        raise ActorNotEmployee
    result = inspection_services.record_inspection(
        operation.id,
        inspection_services.InspectionDTO(
            checked=payload.checked,
            rework=payload.rework,
            scrap=payload.scrap,
            defect_type_id=payload.defect_type_id,
            cause_id=payload.cause_id,
            comment=payload.comment,
            date=payload.date,
        ),
        actor_id=user.id,
        inspector_id=inspector_id,
    )
    created = selectors.get_record(result.record_id)
    assert created is not None
    return Status(
        201,
        InspectionCreatedOut(
            record=_record_out(created),
            warning=REMAKE_WARNING.format(scrap=payload.scrap) if result.needs_remake else "",
        ),
    )


# --- Экран «Качество» -------------------------------------------------------------


@router.get("/summary", response=QualitySummaryOut, operation_id="getQualitySummary")
def get_summary(request: HttpRequest, filters: Query[SummaryFilters]) -> QualitySummaryOut:
    today = timezone.localdate()
    weeks = selectors.last_weeks(today, filters.weeks)
    date_from, date_to = weeks[0], weeks[-1] + timedelta(days=6)
    total = selectors.totals(date_from, date_to)
    final = selectors.totals(date_from, date_to, final=True)
    names = _work_center_names()
    return QualitySummaryOut(
        date_from=date_from,
        date_to=date_to,
        weeks=filters.weeks,
        kpi=QualityKpiOut(
            checked=total.checked,
            defects=total.defects,
            pct=total.pct,
            rework=total.rework,
            scrap=total.scrap,
            early_pct=selectors.percent(total.defects - final.defects, total.defects),
            operator_pct=selectors.percent(total.operator_defects, total.defects),
        ),
        by_work_center=[
            WorkCenterQcOut(
                work_center_id=row.point.work_center_id,
                work_center_name=names.get(row.point.work_center_id, ""),
                point_name=row.point.name,
                is_final=row.point.is_final,
                checked=row.totals.checked,
                defects=row.totals.defects,
                pct=row.totals.pct,
                rework=row.totals.rework,
                scrap=row.totals.scrap,
                top_defect=(
                    TopDefectOut(name=row.top_defect[0], defects=row.top_defect[1])
                    if row.top_defect
                    else None
                ),
                trend=row.trend,
            )
            for row in selectors.summary_by_work_center(weeks)
        ],
        dynamics=[
            WeekQcOut(
                week_start=row.week_start,
                checked=row.checked,
                intermediate_defects=row.intermediate_defects,
                final_defects=row.final_defects,
                pct=row.pct,
            )
            for row in selectors.dynamics(selectors.last_weeks(today, DYNAMICS_WEEKS))
        ],
        pareto_causes=[
            QualityParetoOut(name=r.name, defects=r.defects, cumulative_pct=r.cumulative_pct)
            for r in selectors.pareto_causes(date_from, date_to)
        ],
        pareto_defect_types=[
            QualityParetoOut(name=r.name, defects=r.defects, cumulative_pct=r.cumulative_pct)
            for r in selectors.pareto_defect_types(date_from, date_to)
        ],
    )


@router.get("/records", response=list[JournalRecordOut], operation_id="listInspectionRecords")
def list_records(request: HttpRequest, filters: Query[RecordFilters]) -> list[JournalRecordOut]:
    records = selectors.list_records(
        selectors.RecordFilters(
            date_from=filters.date_from,
            date_to=filters.date_to,
            work_center_id=filters.work_center_id,
            order_id=filters.order_id,
            cause_id=filters.cause_id,
            defects_only=filters.defects_only,
            limit=filters.limit,
        )
    )
    orders = production.get_orders_brief({r.order_id for r in records})
    operations = production.get_operations_brief({r.operation_id for r in records})
    names = _work_center_names()
    result = []
    for record in records:
        order = orders.get(record.order_id)
        operation = operations.get(record.operation_id)
        result.append(
            JournalRecordOut(
                **_record_out(record).model_dump(),
                order_number=order.number if order else "",
                customer_name=order.customer_name if order else "",
                operation_name=f"{operation.seq}. {operation.name}" if operation else "",
                work_center_name=names.get(record.work_center_id, ""),
            )
        )
    return result
