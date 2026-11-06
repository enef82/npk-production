"""Демо-данные приложения по прототипу «Производство»
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8, последний абзац).

Порядок: базовый `seed` ядра (суперпользователь, роли, юрлицо) → подразделения и
сотрудники прототипа (`DEPTS`, `EMP`, `PEOPLE`) с табельными номерами прототипа →
пользователи ролевых персонажей (пароль `demo12345`, роли) → `seed_demo()` фасадов модулей
по порядку. Остальные модули добавляют свои вызовы в `MODULE_SEEDS`.

Сотрудники заводятся здесь, а не в `production`: ими пользуются все модули (табель —
разноской, оборудование — ремонтами), и искать их модули будут по табельному номеру.
Отказывается работать при DEBUG=False, как `seed` ядра. Идемпотентна.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError

from src.analytics import facade as analytics
from src.core.accounts.groups import (
    DESIGNER,
    ESTIMATOR,
    FOREMAN,
    OBSERVER,
    POWER_ENGINEER,
    PROCUREMENT_OFFICER,
    PRODUCTION_HEAD,
    PROJECT_MANAGER,
    QC_ENGINEER,
    TECHNOLOGIST,
    WAREHOUSE_HEAD,
)
from src.core.accounts.models import User
from src.core.org import facade as org
from src.core.org.models import PositionCategory
from src.energy import facade as energy
from src.equipment import facade as equipment
from src.production import facade as production
from src.quality import facade as quality
from src.sales import facade as sales
from src.supply import facade as supply
from src.timesheet import facade as timesheet

DEMO_PASSWORD = "demo12345"  # только для локальной разработки, под DEBUG=True
HIRE_DATE = date(2020, 1, 1)

W, S, M, E = (
    PositionCategory.WORKER,
    PositionCategory.SPECIALIST,
    PositionCategory.MANAGER,
    PositionCategory.EMPLOYEE,
)

# (код, наименование) — `DEPTS` прототипа плюс офис (менеджеры, экономист) и снабжение
# со складом: у сотрудника ядра подразделение обязательно.
DEPARTMENTS = (
    ("OKB", "ОКБ и техподготовка"),
    ("MZU", "Механозаготовительный участок"),
    ("SMU", "Сборочно-монтажный участок"),
    ("OTK", "ОТК"),
    ("COM", "Коммерческий отдел"),
    ("SKL", "Снабжение и склад"),
)


@dataclass(frozen=True)
class DemoEmployee:
    personnel_number: str
    full_name: str
    position: str
    category: PositionCategory
    department: str
    # Ролевой персонаж прототипа (`PEOPLE`): учётная запись и роль.
    email: str = ""
    role: str = ""
    is_staff: bool = False


EMPLOYEES = (
    DemoEmployee(
        "0000101",
        "Белов С.А.",
        "Ведущий инженер-конструктор",
        S,
        "OKB",
        "belov@npk-prod.local",
        DESIGNER,
    ),
    DemoEmployee(
        "0000102",
        "Сидоров К.В.",
        "Инженер-технолог",
        S,
        "OKB",
        "sidorov@npk-prod.local",
        TECHNOLOGIST,
    ),
    DemoEmployee(
        "0000103",
        "Лебедев П.Н.",
        "Программист АСУ ТП",
        S,
        "OKB",
        "lebedev@npk-prod.local",
        OBSERVER,
    ),
    DemoEmployee(
        "0000110", "Гусев И.Д.", "Мастер участка", M, "MZU", "gusev@npk-prod.local", FOREMAN
    ),
    DemoEmployee("0000111", "Ткаченко Р.М.", "Оператор лазерной резки, гибщик", W, "MZU"),
    DemoEmployee("0000112", "Захаров А.П.", "Токарь-оператор ЧПУ", W, "MZU"),
    DemoEmployee("0000113", "Никитин В.С.", "Фрезеровщик-оператор ЧПУ", W, "MZU"),
    DemoEmployee("0000114", "Яковлев Д.И.", "Электросварщик", W, "MZU"),
    DemoEmployee("0000115", "Ершов М.А.", "Электросварщик", W, "MZU"),
    DemoEmployee(
        "0000120",
        "Морозов Д.В.",
        "Начальник производства",
        M,
        "SMU",
        "morozov@npk-prod.local",
        PRODUCTION_HEAD,
        is_staff=True,
    ),
    DemoEmployee("0000121", "Соколова Т.Н.", "Маляр", W, "SMU"),
    DemoEmployee("0000122", "Фролов Е.Г.", "Слесарь-сборщик", W, "SMU"),
    DemoEmployee("0000123", "Павлов С.К.", "Слесарь-сборщик", W, "SMU"),
    DemoEmployee("0000124", "Ильин А.А.", "Сборщик шкафов", W, "SMU"),
    DemoEmployee("0000125", "Тарасов Н.Ю.", "Сборщик шкафов", W, "SMU"),
    DemoEmployee("0000126", "Комаров В.В.", "Электромонтажник", W, "SMU"),
    DemoEmployee("0000127", "Беляев О.И.", "Электромонтажник", W, "SMU"),
    DemoEmployee("0000128", "Кудрявцев Г.С.", "Электромонтажник", W, "SMU"),
    DemoEmployee(
        "0000130", "Орлова Н.В.", "Инженер ОТК", S, "OTK", "orlova@npk-prod.local", QC_ENGINEER
    ),
    DemoEmployee(
        "0000201",
        "Иванов А.",
        "Менеджер проекта",
        S,
        "COM",
        "ivanov@npk-prod.local",
        PROJECT_MANAGER,
    ),
    DemoEmployee(
        "0000202",
        "Зайцева М.",
        "Менеджер проекта",
        S,
        "COM",
        "zaitseva@npk-prod.local",
        PROJECT_MANAGER,
    ),
    DemoEmployee(
        "0000203",
        "Петрова Е.",
        "Экономист-сметчик",
        S,
        "COM",
        "petrova@npk-prod.local",
        ESTIMATOR,
        is_staff=True,
    ),
    DemoEmployee(
        "0000204",
        "Кузнецов В.",
        "Специалист по снабжению",
        S,
        "SKL",
        "kuznetsov@npk-prod.local",
        PROCUREMENT_OFFICER,
    ),
    DemoEmployee(
        "0000205",
        "Шилова Л.",
        "Начальник склада",
        M,
        "SKL",
        "shilova@npk-prod.local",
        WAREHOUSE_HEAD,
    ),
    # В прототипе энергетика нет; без него ручные показания и тарифы на демо-данных
    # были бы видны только администратору.
    DemoEmployee(
        "0000206",
        "Ковалёв Е.Н.",
        "Энергетик",
        S,
        "SMU",
        "kovalev@npk-prod.local",
        POWER_ENGINEER,
    ),
)


# Модули добавляют свои вызовы сюда, в порядке §3.8: production → sales → quality → …
def _work_center_ids() -> dict[str, UUID]:
    """Код участка прототипа (`kb`, `list`, …) → id участка `production`: так модули,
    засеянные позже, связывают свои данные с участками без FK (И2)."""

    return {center.code: center.id for center in production.list_work_centers()}


def _seed_timesheet() -> None:
    order_ids = [o.id for o in production.list_active_orders()] + [
        o.id for o in production.list_shipped_orders(date(2000, 1, 1), date.today())
    ]
    operations = [op for op in production.list_operations_for_orders(order_ids) if not op.is_supply]
    timesheet.seed_demo(
        [(op.order_id, op.id, op.work_center_id) for op in operations],
        work_centers=_work_center_ids(),
        plan_windows={
            op.id: (op.planned_start, op.planned_finish)
            for op in operations
            if op.planned_start is not None and op.planned_finish is not None
        },
    )


MODULE_SEEDS: tuple[tuple[str, Callable[[], object]], ...] = (
    ("production", production.seed_demo),
    ("sales", sales.seed_demo),
    ("timesheet", _seed_timesheet),
    ("quality", quality.seed_demo),
    ("supply", supply.seed_demo),
    ("equipment", lambda: equipment.seed_demo(_work_center_ids())),
    ("energy", energy.seed_demo),
    # Последней: отсечки снимают план, освоение, табель и контроль остальных модулей.
    ("analytics", analytics.seed_demo),
)


class Command(BaseCommand):
    help = "Идемпотентно создаёт демо-данные прототипа «Производство» для разработки."

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("seed_demo запрещён при DEBUG=False — это данные для разработки.")

        call_command("seed", stdout=self.stdout)
        self._seed_people()
        for name, seed in MODULE_SEEDS:
            seed()
            self.stdout.write(f"Демо-данные модуля {name} заведены")
        self.stdout.write(self.style.SUCCESS("Готово."))

    def _seed_people(self) -> None:
        legal_entity = org.get_primary_legal_entity()
        if legal_entity is None:
            raise CommandError("Нет основного юрлица — команда seed ядра не отработала.")
        parent = org.get_department_by_code("production")
        departments = {
            code: org.get_or_create_department(
                org.DepartmentCreateDTO(
                    name=name,
                    code=code,
                    legal_entity_id=legal_entity.pk,
                    parent_id=parent.id if parent else None,
                )
            )
            for code, name in DEPARTMENTS
        }
        for spec in EMPLOYEES:
            user_id = self._user(spec).id if spec.email else None
            position = org.get_or_create_position(spec.position, spec.category)
            org.get_or_create_employee(
                org.EmployeeHireDTO(
                    full_name=spec.full_name,
                    personnel_number=spec.personnel_number,
                    department_id=departments[spec.department].id,
                    position_id=position.id,
                    hire_date=HIRE_DATE,
                    user_id=user_id,
                )
            )

    def _user(self, spec: DemoEmployee) -> User:
        user, created = User.objects.get_or_create(
            email=spec.email,
            defaults={"display_name": spec.full_name, "is_staff": spec.is_staff},
        )
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save(update_fields=["password"])
            user.groups.add(Group.objects.get(name=spec.role))
            self.stdout.write(f"Создан пользователь {spec.email} ({spec.role})")
        return user  # type: ignore[no-any-return]
