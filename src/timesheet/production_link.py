"""Единственная точка, где «Табель» узнаёт о заказах и операциях модуля `production`.

Ветка `timesheet` собрана параллельно с `production`, и `production.facade` в ней
ещё нет — функции ниже возвращают пустой ответ, а сервисы табеля принимают нужные
данные аргументами (`fill_day_from_plan(..., planned)`, `approve_period(...,
order_managers)`, пакеты 1С — `order_numbers`). При слиянии каждая функция становится
одним вызовом фасада, указанным в докстринге; больше табель о `production` нигде не
знает (`docs/adr/0033-timesheet-tabelnyy-nomer-i-svyaz-s-production.md`).

Пустой ответ безопасен: без плана день заполняется накладными, без менеджеров виз не
требуется, без номера заказа аналитика 1С — UUID заказа.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from uuid import UUID

from src.timesheet.calculations import PlannedOp


def planned_operations(work_center_id: UUID | None, day: date) -> list[PlannedOp]:
    """→ `production.facade.list_planned_operations(work_center_id, day)`."""

    return []


def order_managers(order_ids: Iterable[UUID]) -> dict[UUID, UUID]:
    """Заказ → сотрудник-менеджер. → `production.facade.get_orders_brief(ids)[id].manager_id`."""

    return {}


def order_numbers(order_ids: Iterable[UUID]) -> dict[UUID, str]:
    """Заказ → номер для аналитики 1С. → `production.facade.get_orders_brief(ids)[id].number`."""

    return {}
