"""Публичный интерфейс модуля «Ядро: нумерация» для других модулей."""

from __future__ import annotations

from src.core.numbering.services import issue_number

__all__ = [
    "issue_number",
]
