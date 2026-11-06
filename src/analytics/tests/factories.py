from datetime import date
from decimal import Decimal
from uuid import uuid4

import factory
from django.utils import timezone

from src.analytics.models import WeeklyCutoff, WeeklyCutoffRow
from src.core.org.tests.factories import EmployeeFactory


class WeeklyCutoffFactory(factory.django.DjangoModelFactory[WeeklyCutoff]):
    class Meta:
        model = WeeklyCutoff

    week_start = date(2026, 10, 5)  # понедельник
    closed_by = factory.SubFactory(EmployeeFactory)
    closed_at = factory.LazyFunction(timezone.now)


class WeeklyCutoffRowFactory(factory.django.DjangoModelFactory[WeeklyCutoffRow]):
    class Meta:
        model = WeeklyCutoffRow

    cutoff = factory.SubFactory(WeeklyCutoffFactory)
    work_center_id = factory.LazyFunction(uuid4)
    planned_hours = Decimal("40")
    earned_hours = Decimal("36")
    worked_hours = Decimal("38")
    checked = 10
    defects = 1
