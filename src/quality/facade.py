"""Публичный интерфейс модуля «ОТК и качество» для других модулей."""

from __future__ import annotations

from uuid import UUID


def requires_inspection(work_center_id: UUID) -> bool:
    """Есть ли у участка точка контроля (без записи контроля операцию не завизировать).

    Временная реализация до модуля quality, заменяется в волне 2."""

    return False


def has_inspection(operation_id: UUID) -> bool:
    """Есть ли у операции хотя бы одна запись контроля.

    Временная реализация до модуля quality, заменяется в волне 2."""

    return False
