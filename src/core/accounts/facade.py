"""Публичный интерфейс модуля «Ядро: учётные записи» для других модулей.

Роли — Django `Group`; вокабуляр ролей общий для всего приложения и живёт здесь, а не
в модуле, который их проверяет (`docs/spec/00-prilozhenie-proizvodstvo.md` §4).
"""

from __future__ import annotations

from src.core.accounts.rules import (
    is_administrator,
    is_estimator,
    is_foreman,
    is_power_engineer,
    is_procurement_officer,
    is_production_head,
    is_project_manager,
    is_qc_engineer,
    is_technologist,
    is_warehouse_head,
)
from src.core.accounts.selectors import list_user_ids_with_perm

__all__ = [
    "is_administrator",
    "is_estimator",
    "is_foreman",
    "is_power_engineer",
    "is_procurement_officer",
    "is_production_head",
    "is_project_manager",
    "is_qc_engineer",
    "is_technologist",
    "is_warehouse_head",
    "list_user_ids_with_perm",
]
