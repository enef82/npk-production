"""Pydantic-схемы входа и выхода API модуля «Ядро: учётные записи»."""

from __future__ import annotations

from uuid import UUID

from ninja import Schema


class LoginIn(Schema):
    email: str
    password: str


class MeOut(Schema):
    id: UUID
    email: str
    display_name: str
    is_superuser: bool
    roles: list[str]
