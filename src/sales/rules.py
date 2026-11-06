"""Предикаты прав доступа модуля «Заявки и калькуляция» (django-rules,
`docs/spec/00-prilozhenie-proizvodstvo.md` §4).

Менеджер проекта ведёт **свои** заявки (`sales.manage_inquiries` + объектный предикат
`is_order_manager`), экономист — калькуляцию любых (`sales.manage_calculation`), запуск
— начальник производства (`sales.launch_inquiry`). Визу за ответственного ставит тот же,
кто и в производстве (`production.approve_any`, §2.3) — право строкой, без импорта.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import rules

from src.core.accounts.models import User
from src.core.org import facade as org
from src.sales.models import OPEN_STAGES, Inquiry, InquiryStageApproval

_CACHE_ATTR = "_sales_employee_id"
_MISSING = object()


def employee_id_of(user: User) -> UUID | None:
    cached = getattr(user, _CACHE_ATTR, _MISSING)
    if cached is not _MISSING:
        return cached  # type: ignore[return-value]
    employee = org.get_employee_by_user(user.id)
    value = employee.id if employee is not None else None
    setattr(user, _CACHE_ATTR, value)
    return value


@rules.predicate
def is_order_manager(user: User, inquiry: Inquiry | None = None) -> bool:
    """Менеджер заявки (и заказа, который из неё вырастет)."""

    if inquiry is None:
        return False
    return employee_id_of(user) == inquiry.manager_id


@rules.predicate
def is_stage_responsible(user: User, approval: InquiryStageApproval | None = None) -> bool:
    if approval is None or approval.responsible_id is None:
        return False
    return employee_id_of(user) == approval.responsible_id


@rules.predicate
def can_create_inquiries(user: User) -> bool:
    return user.has_perm("sales.manage_inquiries")


@rules.predicate
def can_manage_calculation(user: User) -> bool:
    return user.has_perm("sales.manage_calculation")


@rules.predicate
def can_launch_inquiry(user: User) -> bool:
    return user.has_perm("sales.launch_inquiry")


@rules.predicate
def can_approve_any(user: User) -> bool:
    return user.has_perm("production.approve_any")


class _InquiryLike(Protocol):
    """Заявка или её карточка на доске — у обеих есть этап и менеджер."""

    @property
    def stage(self) -> str: ...

    @property
    def manager_id(self) -> UUID: ...


def can_edit_inquiry(user: User, inquiry: _InquiryLike) -> bool:
    """Реквизиты, перевод, проигрыш — менеджер своей заявки (администратор — любой)."""

    if inquiry.stage not in OPEN_STAGES:
        return False
    is_manager = employee_id_of(user) == inquiry.manager_id
    return user.is_superuser or bool(can_create_inquiries(user) and is_manager)


def can_edit_calculation(user: User, inquiry: _InquiryLike) -> bool:
    if inquiry.stage not in OPEN_STAGES:
        return False
    return bool(can_manage_calculation(user)) or can_edit_inquiry(user, inquiry)


def can_approve_stage(user: User, responsible_id: UUID | None) -> bool:
    me = employee_id_of(user)
    return bool((me is not None and me == responsible_id) or can_approve_any(user))


def can_move_inquiry(user: User, inquiry: _InquiryLike, responsible_id: UUID | None) -> bool:
    if inquiry.stage not in OPEN_STAGES:
        return False
    me = employee_id_of(user)
    return can_edit_inquiry(user, inquiry) or (me is not None and me == responsible_id)
