"""Справочник поставщиков (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4) — заведение
поставщика с экрана «Закупки и склад» в момент заказа."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from src.core.audit.context import actor_context
from src.supply.exceptions import SupplierRequired, SupplierTaken
from src.supply.models import Supplier


def create_supplier(name: str, *, actor_id: UUID) -> UUID:
    name = name.strip()
    if not name:
        raise SupplierRequired("Укажите наименование поставщика.")
    with transaction.atomic(), actor_context(actor_id):
        if Supplier.objects.filter(name__iexact=name).exists():
            raise SupplierTaken
        return Supplier.objects.create(name=name).id
