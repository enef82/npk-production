"""Эндпоинты django-ninja модуля «Энергоучёт» — экран «Энергоучёт» (§3.7, §6;
прототип `renderEnergy`) и приём получасовых интервалов от SCADA.

Права проверяются здесь, сервисы их не проверяют. Чтение — любой
аутентифицированный. Приём SCADA — та же аутентификация, что у остального API,
под техническим пользователем с правом `energy.ingest_intervals`.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from django.http import Http404, HttpRequest
from django.utils import timezone
from ninja import Query, Router

from src.core.common.exceptions import PermissionDenied, ValidationError
from src.energy import selectors
from src.energy.calculations import Balance
from src.energy.models import EnergyResource, Meter, MeterKind, MeterSource
from src.energy.rules import can_ingest_intervals, can_manage_meters
from src.energy.services import ingest as ingest_services
from src.energy.services import meter as meter_services
from src.energy.services import reading as reading_services
from src.energy.services import resource as resource_services

from .filters import PeriodFilters
from .schemas import (
    BalanceDayOut,
    BalanceOut,
    ConsumptionOut,
    DailyOut,
    EnergyAbilitiesOut,
    IngestErrorOut,
    IngestResultOut,
    MeterIn,
    MeterOut,
    MeterTreeRowOut,
    NodeBalanceOut,
    ProfileOut,
    ReadingIn,
    ReadingOut,
    ResourceOut,
    ResourcesOut,
    ScadaEnvelopeIn,
    ScadaMessageOut,
    SpecificOut,
    TariffIn,
    TariffPeriodOut,
)

router = Router(tags=["energy"])

MAX_PERIOD_DAYS = 400


class _AuthenticatedUser(Protocol):
    id: UUID
    is_superuser: bool

    def has_perm(self, perm: str, obj: object = ...) -> bool: ...


class AuthenticatedHttpRequest(HttpRequest):
    auth: _AuthenticatedUser


def _require_manage(user: _AuthenticatedUser) -> None:
    if not can_manage_meters(user):
        raise PermissionDenied("Счётчики, тарифы и показания ведёт энергетик.")


def _period(filters: PeriodFilters) -> tuple[date, date]:
    """По умолчанию — 28 суток до вчерашних включительно (как в прототипе)."""

    yesterday = timezone.localdate() - timedelta(days=1)
    date_to = filters.date_to or yesterday
    date_from = filters.date_from or date_to - timedelta(days=27)
    if date_from > date_to:
        raise ValidationError("Начало периода позже окончания.")
    if (date_to - date_from).days > MAX_PERIOD_DAYS:
        raise ValidationError(f"Период отчёта — не длиннее {MAX_PERIOD_DAYS} суток.")
    return date_from, date_to


def _resource(code: str) -> EnergyResource:
    resource = selectors.get_resource_by_code(code)
    if resource is None:
        raise Http404
    return resource


def _meter(meter_id: UUID) -> Meter:
    meter = selectors.get_meter(meter_id)
    if meter is None:
        raise Http404
    return meter


def _meter_out(meter: Meter) -> MeterOut:
    return MeterOut(
        id=meter.id,
        code=meter.code,
        name=meter.name,
        resource_id=meter.resource_id,
        resource_code=meter.resource.code,
        unit=meter.resource.unit,
        parent_id=meter.parent_id,
        kind=MeterKind(meter.kind),
        equipment_id=meter.equipment_id,
        source=MeterSource(meter.source),
        order=meter.order,
    )


def _balance_out(value: Balance) -> BalanceOut:
    return BalanceOut(
        input=value.input, children=value.children, loss=value.loss, loss_pct=value.loss_pct
    )


# --- Ресурсы и тарифы ---------------------------------------------------------------


@router.get("/resources", response=ResourcesOut, operation_id="listEnergyResources")
def list_resources(request: AuthenticatedHttpRequest) -> ResourcesOut:
    resources = list(selectors.list_resources())
    periods: dict[UUID, list[TariffPeriodOut]] = {r.id: [] for r in resources}
    for period in selectors.list_tariff_periods([r.id for r in resources]):
        periods[period.resource_id].append(
            TariffPeriodOut(valid_from=period.valid_from, tariff=period.tariff)
        )
    return ResourcesOut(
        items=[
            ResourceOut(
                id=r.id,
                code=r.code,
                name=r.name,
                unit=r.unit,
                tariff=r.tariff,
                tariff_periods=periods[r.id],
            )
            for r in resources
        ],
        abilities=EnergyAbilitiesOut(
            can_manage_meters=bool(can_manage_meters(request.auth)),
            can_ingest_intervals=bool(can_ingest_intervals(request.auth)),
        ),
    )


@router.post(
    "/resources/{resource_id}/tariffs", response=ResourcesOut, operation_id="setEnergyTariff"
)
def set_tariff(
    request: AuthenticatedHttpRequest, resource_id: UUID, data: TariffIn
) -> ResourcesOut:
    _require_manage(request.auth)
    if not EnergyResource.objects.filter(id=resource_id).exists():
        raise Http404
    resource_services.set_tariff(
        resource_id, data.valid_from, data.tariff, actor_id=request.auth.id
    )
    return list_resources(request)


# --- Счётчики -----------------------------------------------------------------------


@router.get("/meters", response=list[MeterOut], operation_id="listMeters")
def list_meters(request: HttpRequest, resource: str | None = None) -> list[MeterOut]:
    resource_id = _resource(resource).id if resource else None
    return [_meter_out(meter) for meter in selectors.list_meters(resource_id)]


@router.post("/meters", response=MeterOut, operation_id="createMeter")
def create_meter(request: AuthenticatedHttpRequest, data: MeterIn) -> MeterOut:
    _require_manage(request.auth)
    if not EnergyResource.objects.filter(id=data.resource_id).exists():
        raise ValidationError("Ресурс не найден.")
    meter = meter_services.create_meter(
        meter_services.MeterDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _meter_out(_meter(meter.id))


@router.patch("/meters/{meter_id}", response=MeterOut, operation_id="updateMeter")
def update_meter(request: AuthenticatedHttpRequest, meter_id: UUID, data: MeterIn) -> MeterOut:
    _require_manage(request.auth)
    _meter(meter_id)
    if not EnergyResource.objects.filter(id=data.resource_id).exists():
        raise ValidationError("Ресурс не найден.")
    meter_services.update_meter(
        meter_id, meter_services.MeterDTO(**data.model_dump()), actor_id=request.auth.id
    )
    return _meter_out(_meter(meter_id))


@router.get(
    "/meters/{meter_id}/readings", response=list[ReadingOut], operation_id="listMeterReadings"
)
def list_readings(request: HttpRequest, meter_id: UUID) -> list[ReadingOut]:
    _meter(meter_id)
    return [
        ReadingOut(id=r.id, taken_at=r.taken_at, value=r.value)
        for r in selectors.list_readings(meter_id)
    ]


@router.post("/meters/{meter_id}/readings", response=ReadingOut, operation_id="recordMeterReading")
def record_reading(
    request: AuthenticatedHttpRequest, meter_id: UUID, data: ReadingIn
) -> ReadingOut:
    """Ручной ввод показания: расход с прошлого показания ложится в получасовые
    интервалы между ними."""

    _require_manage(request.auth)
    _meter(meter_id)
    reading = reading_services.record_reading(
        meter_id, data.taken_at, data.value, actor_id=request.auth.id
    )
    return ReadingOut(id=reading.id, taken_at=reading.taken_at, value=reading.value)


# --- Приём от SCADA -----------------------------------------------------------------


@router.post("/intervals", response=IngestResultOut, operation_id="ingestEnergyIntervals")
def ingest_intervals(request: AuthenticatedHttpRequest, data: ScadaEnvelopeIn) -> IngestResultOut:
    """Пакет получасовых интервалов SCADA. Идемпотентно по `message_id`: повтор пакета
    возвращает итог первого приёма с `duplicate = true` и ничего не меняет."""

    if not can_ingest_intervals(request.auth):
        raise PermissionDenied("Интервалы принимаются только от технического пользователя SCADA.")
    result = ingest_services.ingest_intervals(
        ingest_services.ScadaEnvelope(
            schema_version=data.schema_version,
            source_id=data.source_id,
            message_id=data.message_id,
            items=data.items,
        ),
        actor_id=request.auth.id,
    )
    return IngestResultOut(
        message_id=result.message_id,
        duplicate=result.duplicate,
        accepted=result.accepted,
        rejected=result.rejected,
        errors=[IngestErrorOut(**error) for error in result.errors],
    )


@router.get("/scada-messages", response=list[ScadaMessageOut], operation_id="listScadaMessages")
def list_scada_messages(request: HttpRequest) -> list[ScadaMessageOut]:
    """Последние принятые пакеты — строка состояния обмена на экране."""

    return [
        ScadaMessageOut(
            message_id=m.message_id,
            source_id=m.source_id,
            schema_version=m.schema_version,
            items_total=m.items_total,
            items_accepted=m.items_accepted,
            items_rejected=m.items_rejected,
            created_at=m.created_at,
        )
        for m in selectors.list_scada_messages()
    ]


# --- Отчёты -------------------------------------------------------------------------


@router.get(
    "/reports/consumption", response=list[ConsumptionOut], operation_id="getEnergyConsumption"
)
def consumption_report(
    request: HttpRequest,
    filters: PeriodFilters = Query(...),
    resource: str | None = None,
    by_month: bool = False,
) -> list[ConsumptionOut]:
    """Расход и стоимость по ресурсам: по суткам или по месяцам (`by_month`)."""

    date_from, date_to = _period(filters)
    resource_id = _resource(resource).id if resource else None
    return [
        ConsumptionOut(
            resource_id=row.resource.id,
            resource_code=row.resource.code,
            period=row.period,
            quantity=row.quantity,
            cost=row.cost,
        )
        for row in selectors.consumption(
            date_from, date_to, by_month=by_month, resource_id=resource_id
        )
    ]


@router.get("/reports/tree", response=list[MeterTreeRowOut], operation_id="getEnergyMeterTree")
def meter_tree_report(
    request: HttpRequest, resource: str, filters: PeriodFilters = Query(...)
) -> list[MeterTreeRowOut]:
    """«Счётчики и балансы»: дерево, расход за период и предыдущий такой же, доля,
    стоимость, небаланс узла."""

    date_from, date_to = _period(filters)
    return [
        MeterTreeRowOut(
            meter_id=row.meter.id,
            code=row.meter.code,
            name=row.meter.name,
            parent_id=row.meter.parent_id,
            level=row.level,
            kind=MeterKind(row.meter.kind),
            source=MeterSource(row.meter.source),
            quantity=row.quantity,
            previous_quantity=row.previous_quantity,
            share_pct=row.share_pct,
            cost=row.cost,
            balance=_balance_out(row.balance) if row.balance else None,
        )
        for row in selectors.meter_tree(_resource(resource), date_from, date_to)
    ]


@router.get("/reports/daily", response=list[DailyOut], operation_id="getEnergyDaily")
def daily_report(
    request: HttpRequest, resource: str, filters: PeriodFilters = Query(...)
) -> list[DailyOut]:
    date_from, date_to = _period(filters)
    return [
        DailyOut(meter_id=row.meter_id, day=row.day, quantity=row.quantity)
        for row in selectors.daily_series(_resource(resource), date_from, date_to)
    ]


@router.get("/reports/profile", response=ProfileOut, operation_id="getEnergyProfile")
def profile_report(request: HttpRequest, meter_id: UUID, day: date) -> ProfileOut:
    """Получасовой профиль суток: 48 значений расхода (мощность, кВт = значение × 2)."""

    meter = _meter(meter_id)
    values = selectors.day_profile(meter_id, day)
    return ProfileOut(
        meter_id=meter_id,
        day=day,
        unit=meter.resource.unit,
        values=values,
        total=sum(values, Decimal("0")),
    )


@router.get("/reports/balance", response=NodeBalanceOut, operation_id="getEnergyBalance")
def balance_report(
    request: HttpRequest, meter_id: UUID, filters: PeriodFilters = Query(...)
) -> NodeBalanceOut:
    """Баланс узла: ввод − Σ дочерних = потери, за период и по суткам."""

    date_from, date_to = _period(filters)
    result = selectors.node_balance(_meter(meter_id), date_from, date_to)
    children = selectors.list_meters().filter(id__in=[k.id for k in result.children])
    return NodeBalanceOut(
        meter_id=meter_id,
        children=[_meter_out(meter) for meter in children],
        total=_balance_out(result.total),
        days=[BalanceDayOut(day=d.day, balance=_balance_out(d.balance)) for d in result.days],
    )


@router.get("/reports/specific", response=list[SpecificOut], operation_id="getEnergySpecific")
def specific_report(request: HttpRequest, filters: PeriodFilters = Query(...)) -> list[SpecificOut]:
    """Удельный расход электроэнергии оборудования, кВт·ч на машино-час."""

    date_from, date_to = _period(filters)
    return [
        SpecificOut(
            meter_id=row.meter.id,
            meter_code=row.meter.code,
            equipment_id=row.equipment_id,
            equipment_name=row.equipment_name,
            inventory_no=row.inventory_no,
            energy=row.energy,
            machine_hours=row.machine_hours,
            specific=row.specific,
            cost=row.cost,
        )
        for row in selectors.specific_consumption_report(date_from, date_to)
    ]
