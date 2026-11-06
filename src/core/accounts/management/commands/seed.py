"""Идемпотентная демо-загрузка для разработки: суперпользователь, восемь групп,
демо-оргструктура. Отказывается работать при DEBUG=False — это данные для дев-окружения,
не для прод-базы.
"""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError

from src.core.accounts.groups import SEED_GROUP_NAMES
from src.core.accounts.models import User
from src.core.identity import facade as identity
from src.core.identity.models import Item, ItemType, Party, PartyType, UnitOfMeasure
from src.core.org import facade as org
from src.core.org.models import PositionCategory, TaxSystem

DEMO_PARTY_INN = "7700000000"
SUPERUSER_EMAIL = "admin@npk-prod.local"
SUPERUSER_PASSWORD = "admin12345"  # только для локальной разработки, под DEBUG=True


class _DemoParty(TypedDict):
    inn: str
    short_name: str
    party_type: PartyType


class _DemoUom(TypedDict):
    code: str
    name: str
    okei_code: str


class _DemoItem(TypedDict):
    code: str
    name: str
    item_type: ItemType
    uom: str


# Контрагенты и номенклатура для демонстрации DataTable (шаг 10): разные типы,
# чтобы было что сортировать и фильтровать. `create_party` всегда ставит статус
# DRAFT (в `PartyCreateDTO` статуса нет вообще, переход статуса — не предмет
# создания), поэтому варьировать в сиде можно только `party_type`. `inn` подобраны
# так, чтобы не пересекаться друг с другом и с DEMO_PARTY_INN.
DEMO_PARTIES: list[_DemoParty] = [
    {"inn": "7700000001", "short_name": "Альфа Строй", "party_type": PartyType.LEGAL},
    {"inn": "7700000002", "short_name": "Бета Монтаж", "party_type": PartyType.LEGAL},
    {"inn": "770000000305", "short_name": "Гамма Сервис", "party_type": PartyType.ENTREPRE},
    {"inn": "770000000406", "short_name": "Дельта Иванов", "party_type": PartyType.PERSON},
    {"inn": "", "short_name": "Ostrom Trading Ltd", "party_type": PartyType.FOREIGN},
]

DEMO_UOM_CODES: list[_DemoUom] = [
    {"code": "шт", "name": "Штука", "okei_code": "796"},
    {"code": "кг", "name": "Килограмм", "okei_code": "166"},
    {"code": "компл", "name": "Комплект", "okei_code": "839"},
]

DEMO_ITEMS: list[_DemoItem] = [
    {
        "code": "MAT-001",
        "name": "Труба стальная 57х3.5",
        "item_type": ItemType.MATERIAL,
        "uom": "шт",
    },
    {
        "code": "MAT-002",
        "name": "Кабель ВВГ 3х2.5",
        "item_type": ItemType.MATERIAL,
        "uom": "кг",
    },
    {
        "code": "PRD-001",
        "name": "Насос центробежный НЦ-40",
        "item_type": ItemType.PRODUCT,
        "uom": "шт",
    },
    {
        "code": "PRD-002",
        "name": "Щит распределительный ЩР-12",
        "item_type": ItemType.PRODUCT,
        "uom": "компл",
    },
    {
        "code": "SRV-001",
        "name": "Пусконаладочные работы",
        "item_type": ItemType.SERVICE,
        "uom": "шт",
    },
]


class Command(BaseCommand):
    help = (
        "Идемпотентно создаёт демо-данные для разработки: суперпользователя, группы, оргструктуру."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        if not settings.DEBUG:
            raise CommandError("make seed запрещён при DEBUG=False — это данные для разработки.")

        superuser = self._seed_superuser()
        self._seed_groups()
        self._seed_org_structure(superuser.id)
        self._seed_reference_data(superuser.id)

        self.stdout.write(self.style.SUCCESS("Готово."))

    def _seed_superuser(self) -> User:
        superuser, created = User.objects.get_or_create(
            email=SUPERUSER_EMAIL,
            defaults={"display_name": "Администратор", "is_staff": True, "is_superuser": True},
        )
        if created:
            superuser.set_password(SUPERUSER_PASSWORD)
            superuser.save(update_fields=["password"])
            self.stdout.write(f"Создан суперпользователь {SUPERUSER_EMAIL}")
        return superuser  # type: ignore[no-any-return]

    def _seed_groups(self) -> None:
        for name in SEED_GROUP_NAMES:
            Group.objects.get_or_create(name=name)

    def _seed_org_structure(self, admin_user_id: UUID) -> None:
        duplicates = identity.find_party_duplicates(inn=DEMO_PARTY_INN)
        if duplicates:
            party_id = duplicates[0].candidate.id
        else:
            party = identity.create_party(
                identity.PartyCreateDTO(
                    inn=DEMO_PARTY_INN,
                    legal_name="Общество с ограниченной ответственностью «Инжиниринг Строй»",
                    short_name="Инжиниринг Строй",
                    party_type=identity.PartyType.LEGAL,
                ),
                actor_id=admin_user_id,
            )
            party_id = party.id

        legal_entity = org.get_or_create_legal_entity(
            org.LegalEntityCreateDTO(
                party_id=party_id,
                print_name="Инжиниринг Строй",
                tax_system=TaxSystem.OSN,
            )
        )
        org.set_primary_legal_entity(legal_entity.pk)

        head_office = org.get_or_create_department(
            org.DepartmentCreateDTO(
                name="Дирекция", code="head-office", legal_entity_id=legal_entity.pk
            )
        )
        org.get_or_create_department(
            org.DepartmentCreateDTO(
                name="Производство",
                code="production",
                legal_entity_id=legal_entity.pk,
                parent_id=head_office.id,
            )
        )
        org.get_or_create_department(
            org.DepartmentCreateDTO(
                name="Финансы",
                code="finance",
                legal_entity_id=legal_entity.pk,
                parent_id=head_office.id,
            )
        )

        director_position = org.get_or_create_position(
            "Генеральный директор", PositionCategory.MANAGER
        )

        org.get_or_create_employee(
            org.EmployeeHireDTO(
                full_name="Иванов Иван Иванович",
                personnel_number="00001",
                department_id=head_office.id,
                position_id=director_position.id,
                hire_date=date(2020, 1, 1),
                user_id=admin_user_id,
            )
        )

    def _seed_reference_data(self, admin_user_id: UUID) -> None:
        """Контрагенты и номенклатура для демонстрации DataTable/EntityCard (шаг 10) —
        не бизнес-данные, только материал для сортировки, фильтрации и карточки 360°.
        """

        for spec in DEMO_PARTIES:
            # Точное совпадение по short_name, не `find_party_duplicates` — нечёткий поиск
            # здесь непредсказуем (у демо-строк общие подстроки вроде «Строй») и мог бы
            # молча пропустить создание. `force=True` — сознательно: это администраторский
            # сид, а не пользовательский ввод, повторные вызовы `create_party` без force
            # упали бы на том же нечётком совпадении.
            if Party.objects.filter(short_name=spec["short_name"]).exists():
                continue
            identity.create_party(
                identity.PartyCreateDTO(
                    inn=spec["inn"],
                    legal_name=spec["short_name"],
                    short_name=spec["short_name"],
                    party_type=spec["party_type"],
                ),
                actor_id=admin_user_id,
                force=True,
            )

        uom_by_code: dict[str, UnitOfMeasure] = {}
        for uom_spec in DEMO_UOM_CODES:
            uom, _ = UnitOfMeasure.objects.get_or_create(
                code=uom_spec["code"],
                defaults={"name": uom_spec["name"], "okei_code": uom_spec["okei_code"]},
            )
            uom_by_code[uom_spec["code"]] = uom

        for item_spec in DEMO_ITEMS:
            if Item.objects.filter(code=item_spec["code"]).exists():
                continue
            identity.create_item(
                identity.ItemCreateDTO(
                    code=item_spec["code"],
                    name=item_spec["name"],
                    item_type=item_spec["item_type"],
                    base_uom_id=uom_by_code[item_spec["uom"]].id,
                ),
                actor_id=admin_user_id,
                force=True,
            )
