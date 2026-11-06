from datetime import date
from decimal import Decimal

import factory

from src.core.org.tests.factories import DepartmentFactory, EmployeeFactory
from src.timesheet.models import (
    AllocationSource,
    AllocationTarget,
    TimeCode,
    TimesheetPeriod,
    WorkAllocation,
    WorkerProfile,
)


class WorkerProfileFactory(factory.django.DjangoModelFactory[WorkerProfile]):
    class Meta:
        model = WorkerProfile

    employee = factory.SubFactory(EmployeeFactory)
    work_center_id = None
    hourly_rate = Decimal("1000")


class WorkAllocationFactory(factory.django.DjangoModelFactory[WorkAllocation]):
    class Meta:
        model = WorkAllocation

    employee = factory.SubFactory(EmployeeFactory)
    date = date(2026, 9, 1)
    time_code = factory.LazyFunction(lambda: TimeCode.objects.get(code="Я"))
    target = AllocationTarget.OVERHEAD
    order_id = None
    operation_id = None
    hours = Decimal("8")
    source = AllocationSource.MANUAL
    source_ref = ""


class TimesheetPeriodFactory(factory.django.DjangoModelFactory[TimesheetPeriod]):
    class Meta:
        model = TimesheetPeriod

    department = factory.SubFactory(DepartmentFactory)
    month = date(2026, 9, 1)
