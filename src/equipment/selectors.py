"""Запросы на чтение и отчёты модуля «Оборудование и ТО» (§3.6): моточасы, состояние
ТО, недельная сводка, Парето простоев, журнал аварий и ремонтов.

Каждый отчёт — фиксированное число запросов независимо от числа станков (N+1
недопустим): журналы читаются одним запросом на диапазон и раскладываются в Python.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from django.db.models import (
    DecimalField,
    F,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
    Window,
)
from django.db.models.functions import Coalesce, RowNumber
from django.utils import timezone

from src.equipment.calculations import (
    AVG_RUN_WINDOW,
    MaintenanceForecast,
    WeekSummary,
    average_run,
    forecast_maintenance,
    hours_between,
    summarize_week,
)
from src.equipment.models import (
    DownReason,
    Equipment,
    FailureCategory,
    IdleReason,
    MaintenanceRecord,
    MaintenanceState,
    MaintenanceType,
    Repair,
    RepairKind,
    RepairStatus,
    RepairWorker,
    RuntimeLog,
)

ZERO = Decimal("0")
_HOURS_FIELD: DecimalField[Decimal, Decimal] = DecimalField(max_digits=14, decimal_places=2)


# --- Справочники -----------------------------------------------------------------


def list_idle_reasons() -> QuerySet[IdleReason]:
    return IdleReason.objects.filter(is_active=True)


def list_down_reasons() -> QuerySet[DownReason]:
    return DownReason.objects.filter(is_active=True)


def list_failure_categories() -> QuerySet[FailureCategory]:
    return FailureCategory.objects.filter(is_active=True)


# --- Оборудование и моточасы --------------------------------------------------------


def list_equipment() -> QuerySet[Equipment]:
    """Оборудование с суммой работы по журналу (`run_total`) — моточасы без N+1."""

    return Equipment.objects.annotate(
        run_total=Coalesce(Sum("runtime_logs__run"), Value(ZERO), output_field=_HOURS_FIELD)
    ).order_by("inventory_no")


def get_equipment(equipment_id: UUID) -> Equipment | None:
    return list_equipment().filter(id=equipment_id).first()


def operating_hours(equipment: Equipment) -> Decimal:
    """Моточасы = начальные + Σ работы. Ожидает `run_total` из `list_equipment()`."""

    run_total: Decimal = getattr(equipment, "run_total", ZERO)
    return equipment.operating_hours_initial + run_total


def current_operating_hours(equipment_id: UUID) -> Decimal:
    equipment = get_equipment(equipment_id)
    return operating_hours(equipment) if equipment is not None else ZERO


def last_runs_by_equipment(equipment_ids: list[UUID]) -> dict[UUID, list[Decimal]]:
    """Последние `AVG_RUN_WINDOW` значений работы по каждому станку — одним запросом
    с оконной функцией."""

    rows = (
        RuntimeLog.objects.filter(equipment_id__in=equipment_ids)
        .annotate(rn=Window(RowNumber(), partition_by=F("equipment_id"), order_by=F("date").desc()))
        .filter(rn__lte=AVG_RUN_WINDOW)
        .order_by("equipment_id", "-date")
        .values_list("equipment_id", "run")
    )
    result: dict[UUID, list[Decimal]] = defaultdict(list)
    for equipment_id, run in rows:
        result[equipment_id].append(run)
    return result


# --- ТО ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MaintenanceRow:
    maintenance_type: MaintenanceType
    last_date: date | None
    last_at_hours: Decimal | None
    forecast: MaintenanceForecast


def _maintenance_types(equipment_ids: list[UUID]) -> QuerySet[MaintenanceType]:
    last = MaintenanceRecord.objects.filter(maintenance_type=OuterRef("pk")).order_by(
        "-date", "-created_at"
    )
    return (
        MaintenanceType.objects.filter(equipment_id__in=equipment_ids)
        .annotate(
            last_date=Subquery(last.values("date")[:1]),
            last_at_hours=Subquery(last.values("at_hours")[:1]),
        )
        .order_by("equipment_id", "interval_hours", "code")
    )


def maintenance_by_equipment(
    equipment: list[Equipment], today: date
) -> dict[UUID, list[MaintenanceRow]]:
    """Состояние ТО каждого вида (`toState`), отсортировано по остатку — первым идёт
    ближайшее. `equipment` — из `list_equipment()` (с `run_total`)."""

    ids = [item.id for item in equipment]
    hours = {item.id: operating_hours(item) for item in equipment}
    runs = last_runs_by_equipment(ids)
    result: dict[UUID, list[MaintenanceRow]] = defaultdict(list)
    for mtype in _maintenance_types(ids):
        last_date: date | None = getattr(mtype, "last_date", None)
        last_at: Decimal | None = getattr(mtype, "last_at_hours", None)
        forecast = forecast_maintenance(
            interval_hours=mtype.interval_hours,
            last_at_hours=last_at,
            current_hours=hours[mtype.equipment_id],
            avg_run=average_run(runs.get(mtype.equipment_id, [])),
            today=today,
        )
        result[mtype.equipment_id].append(MaintenanceRow(mtype, last_date, last_at, forecast))
    for rows in result.values():
        rows.sort(key=lambda row: row.forecast.hours_left)
    return result


@dataclass(frozen=True)
class MaintenancePlanRow:
    equipment: Equipment
    row: MaintenanceRow


def maintenance_plan(today: date, horizon_days: int = 30) -> list[MaintenancePlanRow]:
    """План ТО на `horizon_days` дней: всё, что по прогнозу наступит до горизонта."""

    equipment = list(list_equipment())
    states = maintenance_by_equipment(equipment, today)
    horizon = today + timedelta(days=horizon_days)
    plan = [
        MaintenancePlanRow(item, row)
        for item in equipment
        for row in states.get(item.id, [])
        if row.forecast.due_date <= horizon
    ]
    plan.sort(key=lambda entry: (entry.row.forecast.due_date, entry.row.forecast.hours_left))
    return plan


# --- Наработка --------------------------------------------------------------------


def runtime_logs(
    equipment_id: UUID, date_from: date | None = None, date_to: date | None = None
) -> QuerySet[RuntimeLog]:
    qs = RuntimeLog.objects.filter(equipment_id=equipment_id).select_related(
        "idle_reason", "down_reason"
    )
    if date_from is not None:
        qs = qs.filter(date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(date__lte=date_to)
    return qs.order_by("-date")


def runtime_between(date_from: date, date_to: date) -> list[RuntimeLog]:
    return list(
        RuntimeLog.objects.filter(date__gte=date_from, date__lte=date_to).order_by(
            "equipment_id", "date"
        )
    )


def week_summaries(
    equipment_ids: list[UUID], weeks: list[date]
) -> dict[UUID, dict[date, WeekSummary]]:
    """`machWeek` по каждому станку и каждой неделе (понедельник) — одним запросом."""

    if not weeks:
        return {}
    rows = RuntimeLog.objects.filter(
        equipment_id__in=equipment_ids,
        date__gte=min(weeks),
        date__lte=max(weeks) + timedelta(days=6),
    ).values_list("equipment_id", "date", "run", "setup", "idle", "down")
    buckets: dict[tuple[UUID, date], list[tuple[Decimal, Decimal, Decimal, Decimal]]] = defaultdict(
        list
    )
    for equipment_id, day, run, setup, idle, down in rows:
        monday = day - timedelta(days=day.weekday())
        buckets[(equipment_id, monday)].append((run, setup, idle, down))
    return {
        equipment_id: {
            week: summarize_week(buckets.get((equipment_id, week), [])) for week in weeks
        }
        for equipment_id in equipment_ids
    }


@dataclass(frozen=True)
class ParetoRow:
    reason: str
    is_down: bool  # отказ/остановка (красный в прототипе), иначе простой
    hours: Decimal


def downtime_pareto(date_from: date, date_to: date) -> list[ParetoRow]:
    """Парето простоев: простой по причинам простоя + отказы по причинам остановки,
    по убыванию часов."""

    logs = RuntimeLog.objects.filter(date__gte=date_from, date__lte=date_to)
    idle = (
        logs.filter(idle__gt=0)
        .values("idle_reason__name")
        .annotate(hours=Sum("idle"))
        .values_list("idle_reason__name", "hours")
    )
    down = (
        logs.filter(down__gt=0)
        .values("down_reason__name")
        .annotate(hours=Sum("down"))
        .values_list("down_reason__name", "hours")
    )
    rows = [ParetoRow(name, False, hours) for name, hours in idle]
    rows += [ParetoRow(name, True, hours) for name, hours in down]
    rows.sort(key=lambda row: (-row.hours, row.reason))
    return rows


# --- Аварии и ремонты ---------------------------------------------------------------


def _repairs() -> QuerySet[Repair]:
    return (
        Repair.objects.select_related("equipment", "category", "maintenance_type")
        .prefetch_related(
            Prefetch(
                "workers",
                queryset=RepairWorker.objects.select_related("employee").order_by(
                    "-hours", "employee__full_name"
                ),
            )
        )
        .annotate(
            labor_hours=Coalesce(Sum("workers__hours"), Value(ZERO), output_field=_HOURS_FIELD)
        )
    )


def get_repair(repair_id: UUID) -> Repair | None:
    return _repairs().filter(id=repair_id).first()


def list_repairs(
    *,
    date_from: date | None = None,
    kind: RepairKind | None = None,
    equipment_id: UUID | None = None,
) -> QuerySet[Repair]:
    """Журнал (`repairsPanel`): за период — по дате начала; незакрытые — всегда.
    Сначала незакрытые, затем по убыванию начала."""

    qs = _repairs()
    if date_from is not None:
        start = timezone.make_aware(datetime.combine(date_from, datetime.min.time()))
        qs = qs.filter(Q(started_at__gte=start) | ~Q(status=RepairStatus.DONE))
    if kind is not None:
        qs = qs.filter(kind=kind)
    if equipment_id is not None:
        qs = qs.filter(equipment_id=equipment_id)
    return qs.order_by("-started_at")


def repair_downtime(repair: Repair, now: datetime | None = None) -> Decimal:
    """Простой = окончание − начало; у незакрытой — до текущего момента."""

    finish = repair.finished_at or now or timezone.now()
    return hours_between(repair.started_at, finish)


def repair_labor(repair: Repair) -> Decimal:
    labor: Decimal = getattr(repair, "labor_hours", ZERO)
    return labor


@dataclass(frozen=True)
class RepairsSummary:
    failures: int
    failure_downtime: Decimal
    labor_hours: Decimal
    mttr: Decimal  # среднее время восстановления по закрытым авариям, ч
    mtbf: Decimal | None  # наработка на отказ, машино-часы работы / число аварий
    downtime_by_category: list[tuple[str, Decimal]]
    failures_by_equipment: list[tuple[UUID, str, int]]


def summarize_repairs(
    repairs: list[Repair], *, date_from: date, equipment_id: UUID | None, now: datetime
) -> RepairsSummary:
    failures = [r for r in repairs if r.kind == RepairKind.FAILURE]
    failure_downtime = sum((repair_downtime(r, now) for r in failures), ZERO)
    labor = sum((repair_labor(r) for r in repairs), ZERO)
    closed = [r for r in failures if r.status == RepairStatus.DONE]
    mttr = (
        (sum((repair_downtime(r, now) for r in closed), ZERO) / len(closed)).quantize(
            Decimal("0.1")
        )
        if closed
        else ZERO
    )
    logs = RuntimeLog.objects.filter(date__gte=date_from)
    if equipment_id is not None:
        logs = logs.filter(equipment_id=equipment_id)
    run_hours = logs.aggregate(total=Sum("run"))["total"] or ZERO
    mtbf = (run_hours / len(failures)).quantize(Decimal("1")) if failures else None

    by_category: dict[str, Decimal] = defaultdict(lambda: ZERO)
    by_equipment: dict[UUID, tuple[str, int]] = {}
    for repair in failures:
        if repair.category is not None:
            by_category[repair.category.name] += repair_downtime(repair, now)
        name, count = by_equipment.get(repair.equipment_id, (repair.equipment.name, 0))
        by_equipment[repair.equipment_id] = (name, count + 1)
    return RepairsSummary(
        failures=len(failures),
        failure_downtime=failure_downtime,
        labor_hours=labor,
        mttr=mttr,
        mtbf=mtbf,
        downtime_by_category=sorted(by_category.items(), key=lambda item: -item[1]),
        failures_by_equipment=sorted(
            ((eq_id, name, count) for eq_id, (name, count) in by_equipment.items()),
            key=lambda item: (-item[2], item[1]),
        ),
    )


def has_open_repairs(equipment_id: UUID, *, maintenance: bool) -> bool:
    qs = Repair.objects.filter(equipment_id=equipment_id).exclude(status=RepairStatus.DONE)
    if maintenance:
        return qs.filter(kind=RepairKind.MAINTENANCE).exists()
    return qs.exclude(kind=RepairKind.MAINTENANCE).exists()


# --- Сводка экрана ------------------------------------------------------------------


@dataclass(frozen=True)
class DashboardKpi:
    equipment_count: int
    utilization: Decimal  # средняя загрузка за неделю, доля
    idle_and_down_hours: Decimal
    maintenance_overdue: int
    maintenance_soon: int


def dashboard_kpi(
    equipment: list[Equipment],
    week: dict[UUID, WeekSummary],
    states: dict[UUID, list[MaintenanceRow]],
) -> DashboardKpi:
    count = len(equipment)
    summaries = [week[item.id] for item in equipment if item.id in week]
    utilization = (
        (sum((s.utilization for s in summaries), ZERO) / count).quantize(Decimal("0.0001"))
        if count
        else ZERO
    )
    idle_down = sum((s.idle + s.down for s in summaries), ZERO)
    all_rows = [row for rows in states.values() for row in rows]
    return DashboardKpi(
        equipment_count=count,
        utilization=utilization,
        idle_and_down_hours=idle_down,
        maintenance_overdue=sum(
            1 for row in all_rows if row.forecast.state == MaintenanceState.OVERDUE
        ),
        maintenance_soon=sum(1 for row in all_rows if row.forecast.state == MaintenanceState.SOON),
    )
