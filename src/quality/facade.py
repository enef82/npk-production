"""Публичный интерфейс модуля «ОТК и качество» для других модулей
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.3, «Фасад»).

Наружу — только датаклассы этого файла и UUID (И1).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from src.quality import selectors

__all__ = [
    "QcAgg",
    "QcWeekRow",
    "get_qc_by_operation",
    "has_inspection",
    "list_qc_by_week",
    "requires_inspection",
    "seed_demo",
]


@dataclass(frozen=True)
class QcAgg:
    checked: int
    rework: int
    scrap: int
    # Брак с причиной «по вине оператора» — для выработки сотрудника (§3.8).
    operator_defects: int

    @property
    def defects(self) -> int:
        return self.rework + self.scrap


@dataclass(frozen=True)
class QcWeekRow:
    week_start: date
    work_center_id: UUID
    is_final: bool
    checked: int
    rework: int
    scrap: int
    operator_defects: int


def requires_inspection(work_center_id: UUID) -> bool:
    """Есть ли у участка действующая точка контроля — без записи контроля операцию
    участка не завизировать (§3.1, «Операции»)."""

    return selectors.get_point_for_work_center(work_center_id) is not None


def has_inspection(operation_id: UUID) -> bool:
    """Есть ли у операции хотя бы одна запись контроля."""

    return selectors.has_inspection(operation_id)


def get_qc_by_operation(ids: Iterable[UUID]) -> dict[UUID, QcAgg]:
    """Агрегат контроля по операциям; операций без записей в ответе нет."""

    return {
        operation_id: QcAgg(
            checked=t.checked,
            rework=t.rework,
            scrap=t.scrap,
            operator_defects=t.operator_defects,
        )
        for operation_id, t in selectors.qc_by_operation(ids).items()
    }


def list_qc_by_week(date_from: date, date_to: date) -> list[QcWeekRow]:
    """Контроль по неделе (с понедельника) и участку за записи с датой в [from, to]."""

    final = {p.work_center_id for p in selectors.list_points(active_only=False) if p.is_final}
    return [
        QcWeekRow(
            week_start=row.week_start,
            work_center_id=row.work_center_id,
            is_final=row.work_center_id in final,
            checked=row.totals.checked,
            rework=row.totals.rework,
            scrap=row.totals.scrap,
            operator_defects=row.totals.operator_defects,
        )
        for row in selectors.week_rows(date_from, date_to)
    ]


def seed_demo() -> None:
    """Точки контроля прототипа (`QCP`) с видами дефектов и записи контроля по
    выполненным и идущим операциям демо-заказов (`qcSeed`), плюс история брака за
    12 недель. Запускать после `production.facade.seed_demo()`."""

    # Импорт при вызове: демо читает заказы через `production.facade`, а `production`
    # импортирует этот фасад при загрузке (виза операции) — на уровне модуля это цикл.
    from src.quality.services import demo as demo_services

    demo_services.seed_demo()
