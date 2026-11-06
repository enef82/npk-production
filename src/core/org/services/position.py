"""Position — простой справочник, обычный CRUD ведётся через админку напрямую.

Единственная нужная здесь функция — идемпотентное получение-или-создание для `seed`,
у которого, в отличие от админки, нет прямого доступа к `core.org.models` (инвариант И1,
доступ другим модулям — только через `facade.py`).
"""

from __future__ import annotations

from django.db import transaction

from src.core.org.models import Position, PositionCategory


def get_or_create_position(name: str, category: PositionCategory, *, grade: str = "") -> Position:
    with transaction.atomic():
        position, _ = Position.objects.get_or_create(
            name=name,
            category=category,
            defaults={"grade": grade},
        )

    return position
