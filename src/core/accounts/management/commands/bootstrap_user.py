"""Бутстрап одной учётной записи для прод-контура (docs/adr/0030-publikatsiya-v-internet.md,
мера 2; задание ИС «прод-контур», часть C, п. 6). Работает по одному человеку за вызов —
пятнадцати человек списком нет, заводить их пачкой рано.

Пароль генерируется самой командой и печатается один раз в вывод — не принимается
аргументом: аргументы командной строки остаются в истории шелла (`.bash_history` и
аналоги), а публичная форма входа (ADR 0030) делает предсказуемые пароли вида
«Иванов2026» реальным риском, не гипотетическим.

`make seed` для этой команды не альтернатива и не образец: `seed` — идемпотентный
демо-посев для разработки (отказывается работать при `DEBUG=False`), эта команда —
разовое администраторское действие на настоящих людях."""

from __future__ import annotations

import datetime
from typing import Any

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.crypto import get_random_string

from src.core.accounts.groups import SEED_GROUP_NAMES
from src.core.accounts.models import User
from src.core.org import facade as org
from src.core.org.models import PositionCategory

# Без 0/O, 1/l/I — пароль читают глазами при передаче лично, путаница в этих
# символах не должна быть причиной, почему человек не может войти в первый день.
_PASSWORD_ALPHABET = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"


class Command(BaseCommand):
    help = "Заводит одну учётную запись: пользователь + сотрудник (Employee) + роль."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--display-name", required=True, help="ФИО для отображения")
        parser.add_argument("--full-name", required=True, help="Полное ФИО сотрудника")
        parser.add_argument("--personnel-number", required=True, help="Табельный номер")
        parser.add_argument("--department-code", required=True, help="Department.code")
        parser.add_argument("--position", required=True, help="Название должности")
        parser.add_argument(
            "--position-category",
            required=True,
            choices=[c.value for c in PositionCategory],
        )
        parser.add_argument(
            "--role",
            required=True,
            choices=list(SEED_GROUP_NAMES),
            help="Роль по §6 спецификации CRM (спец. CRM ИС)",
        )
        parser.add_argument(
            "--hire-date",
            default=None,
            help="ГГГГ-МММ-ДД, по умолчанию — сегодня",
        )
        parser.add_argument(
            "--is-staff",
            action="store_true",
            help="Доступ в Django Admin",
        )
        parser.add_argument(
            "--superuser",
            action="store_true",
            help="Суперпользователь — только для самой первой учётной записи",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        email: str = options["email"]

        if User.objects.filter(email=email).exists():
            raise CommandError(
                f"Пользователь {email} уже существует — команда не перезаписывает "
                "пароль существующей учётной записи. Смена пароля — отдельное действие."
            )

        # Подразделение обязано существовать заранее (оргструктура заводится не этой
        # командой) — по коду, не по имени, совпадения имён в реальной оргструктуре
        # не исключены, а код по построению уникален (Department.code, unique=True).
        department = org.get_department_by_code(options["department_code"])
        if department is None:
            raise CommandError(
                f"Подразделение с кодом «{options['department_code']}» не найдено. "
                "Оргструктура заводится отдельно, эта команда её не создаёт."
            )
        department_id = department.id

        position = org.get_or_create_position(
            options["position"], PositionCategory(options["position_category"])
        )

        hire_date = (
            datetime.date.fromisoformat(options["hire_date"])
            if options["hire_date"]
            else datetime.date.today()
        )

        if options["role"] not in SEED_GROUP_NAMES:
            raise CommandError(f"Неизвестная роль: {options['role']}")
        group, _ = Group.objects.get_or_create(name=options["role"])

        password = get_random_string(20, allowed_chars=_PASSWORD_ALPHABET)

        # Суперпользователь без доступа в админку — противоречивое состояние
        # (is_superuser сам по себе не даёт войти в /admin/), поэтому superuser
        # всегда тянет за собой is_staff, даже если флаг не передан явно.
        is_staff = options["is_staff"] or options["superuser"]

        user = User.objects.create_user(
            email=email,
            password=password,
            display_name=options["display_name"],
            is_staff=is_staff,
            is_superuser=options["superuser"],
        )
        user.groups.add(group)

        org.hire_employee(
            org.EmployeeHireDTO(
                full_name=options["full_name"],
                personnel_number=options["personnel_number"],
                department_id=department_id,
                position_id=position.id,
                hire_date=hire_date,
                user_id=user.id,
            )
        )

        self.stdout.write(self.style.SUCCESS(f"Учётная запись создана: {email}"))
        self.stdout.write(self.style.WARNING(f"Пароль (показывается один раз): {password}"))
