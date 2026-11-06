"""Демо-заявки — перенос `seed()` прототипа (`docs/spec/00-prilozhenie-proizvodstvo.md`
§3.8, последний абзац): 24 заявки на этапах «Новые», «Просчёт», «Согласование КП» и
запущенные в работу, калькуляция из шаблонов, предварительные планы, визы этапов.
Детерминированно, даты — относительно сегодняшнего дня.

Запускается после `production.facade.seed_demo()`: шаблоны и заказы уже есть. Связь с
заказами — по детерминированным идентификаторам (`uuid5` от номера заявки, тот же
приём в `production.services.demo`), без чтения чужих моделей: даты запущенной заявки
берутся из `production.facade.get_orders_brief`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from django.db import transaction
from django.utils import timezone

from src.core.common.exceptions import ConflictError
from src.core.common.scheduling import add_working_days
from src.core.identity import facade as identity
from src.core.identity.models import Party
from src.core.numbering.models import Numerator, NumeratorCounter
from src.core.org.models import Employee
from src.production import facade as production
from src.sales.models import (
    INQUIRY_STAGE_SEQUENCE,
    CalcMaterial,
    CalcOperation,
    Inquiry,
    InquiryStage,
    InquiryStageApproval,
    LossReason,
    SalesSettings,
)
from src.sales.services.calculation import replace_calculation, schedule_inquiry

# Тот же namespace, что в `production.services.demo` — так заявка и заказ демо-набора
# находят друг друга без обращения к чужим моделям.
DEMO_NAMESPACE = UUID("5f0c3a52-7d4e-5b8a-9e61-2c4b1d7a9f30")

PERSONNEL = {
    "Иванов А.": "0000201",
    "Зайцева М.": "0000202",
    "Петрова Е.": "0000203",
}

LOSS_REASONS = ("Цена", "Срок", "Выбрали другого поставщика", "Отказ от закупки")


@dataclass(frozen=True)
class DemoInquiry:
    number: str
    customer: str
    object_name: str
    template: str
    quantity: int
    manager: str
    stage: InquiryStage
    # Срок — календарных дней от сегодня; для запущенных берётся из заказа.
    due_days: int = 0
    # Предварительный старт — рабочих дней от сегодня; `None` — плана нет.
    plan_offset: int | None = None
    with_calc: bool = True
    drop_last_material: bool = False
    one_person_ops: tuple[int, ...] = ()


L = InquiryStage.LAUNCHED

INQUIRIES = (
    DemoInquiry(
        "З-0418",
        "АО «Уралхимпласт»",
        "Насосная станция оборотного водоснабжения",
        "ШУ",
        2,
        "Иванов А.",
        InquiryStage.NEW,
        60,
        with_calc=False,
    ),
    DemoInquiry(
        "З-0419",
        "ООО «ЕвразЭнергоТранс»",
        "ТП-14, корпуса шкафов",
        "ЛИСТ",
        12,
        "Зайцева М.",
        InquiryStage.NEW,
        40,
        with_calc=False,
    ),
    DemoInquiry(
        "З-0414",
        "МУП «Водоканал» Березовский",
        "КНС-3, механическая очистка",
        "ОБОР",
        1,
        "Иванов А.",
        InquiryStage.CALC,
        95,
        drop_last_material=True,
    ),
    DemoInquiry(
        "З-0411",
        "ПАО «Т Плюс»",
        "ТЭЦ-2, система постоянного тока",
        "ШОТ",
        2,
        "Зайцева М.",
        InquiryStage.APPROVAL,
        62,
        plan_offset=8,
    ),
    DemoInquiry(
        "З-0421",
        "АО «Синарский трубный завод»",
        "Втулки и фланцы, 60 шт.",
        "МЕХ",
        60,
        "Зайцева М.",
        InquiryStage.APPROVAL,
        55,
        plan_offset=12,
    ),
    DemoInquiry(
        "З-0423",
        "ЕМУП «Водоканал»",
        "КНС «Широкая речка», 2 решётки",
        "ОБОР",
        2,
        "Иванов А.",
        InquiryStage.CALC,
        130,
        plan_offset=22,
    ),
    DemoInquiry(
        "З-0427",
        "АО «Уралкалий»",
        "Насосная станция, 6 шкафов",
        "ШУ",
        6,
        "Иванов А.",
        InquiryStage.CALC,
        110,
        plan_offset=28,
    ),
    DemoInquiry(
        "З-0429",
        "ООО «Водоканал Первоуральск»",
        "КНС-2, решётка",
        "ОБОР",
        1,
        "Зайцева М.",
        InquiryStage.APPROVAL,
        100,
        plan_offset=18,
    ),
    DemoInquiry(
        "З-0430",
        "ООО «Электрощит-Урал»",
        "Корпуса щитов, 50 шт.",
        "ЛИСТ",
        50,
        "Зайцева М.",
        InquiryStage.NEW,
        70,
        with_calc=False,
    ),
    DemoInquiry(
        "З-0425", "АО «Облкоммунэнерго»", "РП-21, НКУ", "НКУ", 4, "Иванов А.", InquiryStage.CALC, 80
    ),
    # Запущенные — заказы заводит `production.seed_demo`.
    DemoInquiry("З-0402", "АО «Святогор»", "ПС 110 кВ «Обогатительная»", "РЗА", 2, "Иванов А.", L),
    DemoInquiry(
        "З-0399", "ООО «Водоканал-НТ»", "КНС-12, решётка-дробилка", "ОБОР", 1, "Зайцева М.", L
    ),
    DemoInquiry("З-0396", "ООО «УГМК-Холдинг»", "Котельная промплощадки", "ВРУ", 4, "Иванов А.", L),
    DemoInquiry(
        "З-0393", "АО «Уралмашзавод»", "Валы приводные, 20 шт.", "МЕХ", 20, "Зайцева М.", L
    ),
    DemoInquiry(
        "З-0390",
        "АО «Уралэлектромедь»",
        "Цех электролиза, вентиляция",
        "ШУ",
        3,
        "Иванов А.",
        L,
        one_person_ops=(4,),
    ),
    DemoInquiry(
        "З-0381", "ООО «Газпром трансгаз Екатеринбург»", "ГРС «Северная»", "НКУ", 1, "Зайцева М.", L
    ),
    DemoInquiry("З-0377", "АО «ЕЭСК»", "РП-7", "ВРУ", 2, "Иванов А.", L),
    DemoInquiry(
        "З-0384",
        "АО «Камышловский завод „Урализолятор“»",
        "Сушильная камера, автоматика",
        "ШУ",
        4,
        "Иванов А.",
        L,
    ),
    DemoInquiry(
        "З-0386", "ООО «Водоканал Асбест»", "КНС-5, решётка-дробилка", "ОБОР", 1, "Зайцева М.", L
    ),
    DemoInquiry("З-0388", "АО «Уралхиммаш»", "Оси и втулки, 40 шт.", "МЕХ", 40, "Зайцева М.", L),
    DemoInquiry("З-0392", "ООО «Элмаш»", "Корпуса пультов, 30 шт.", "ЛИСТ", 30, "Иванов А.", L),
    DemoInquiry("З-0395", "АО «ЕЭнС»", "ТП-31, НКУ 0,4 кВ", "НКУ", 3, "Иванов А.", L),
    DemoInquiry(
        "З-0397",
        "МУП «Водоканал» г. Ревда",
        "Очистные сооружения, 2 решётки",
        "ОБОР",
        2,
        "Зайцева М.",
        L,
    ),
    DemoInquiry("З-0400", "ОАО «МРСК Урала»", "ПС 35 кВ «Садовая»", "РЗА", 1, "Иванов А.", L),
)


def _at(day: date, hour: int) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


def _employees() -> dict[str, Employee]:
    found = {
        e.personnel_number: e
        for e in Employee.objects.filter(personnel_number__in=PERSONNEL.values())
    }
    missing = [name for name, tab in PERSONNEL.items() if tab not in found]
    if missing:
        raise ConflictError(
            "Нет сотрудников демо-набора: " + ", ".join(missing) + ". Запустите команду seed_demo."
        )
    return {name: found[tab] for name, tab in PERSONNEL.items()}


def _party_id(name: str, actor_id: UUID) -> UUID:
    existing = Party.objects.filter(short_name=name).first()
    if existing is not None:
        return existing.id
    party = identity.create_party(
        identity.PartyCreateDTO(legal_name=name, short_name=name), actor_id=actor_id, force=True
    )
    return party.id


def _seed_reference(people: dict[str, Employee]) -> None:
    for index, name in enumerate(LOSS_REASONS):
        LossReason.objects.get_or_create(name=name, defaults={"sort_order": index})
    settings, _ = SalesSettings.objects.get_or_create()
    if settings.economist_id is None:
        settings.economist = people["Петрова Е."]
        settings.save()


def _seed_inquiry(
    spec: DemoInquiry, people: dict[str, Employee], actor_id: UUID, today: date
) -> None:
    inquiry_id = uuid5(DEMO_NAMESPACE, f"inquiry/{spec.number}")
    if Inquiry.objects.filter(id=inquiry_id).exists():
        return
    template = production.get_template(spec.template)
    if template is None:
        raise ConflictError("Нет шаблонов изделий — сначала production.facade.seed_demo().")
    launched = spec.stage == InquiryStage.LAUNCHED
    order_id: UUID | None = None
    planned_start = (
        add_working_days(today, spec.plan_offset) if spec.plan_offset is not None else None
    )
    due = today + timedelta(days=spec.due_days)
    created = today
    if launched:
        order_id = uuid5(DEMO_NAMESPACE, f"order/{spec.number}")
        order = production.get_orders_brief([order_id]).get(order_id)
        if order is None:
            raise ConflictError(
                f"Нет заказа по заявке {spec.number} — сначала production.facade.seed_demo()."
            )
        planned_start, due = order.planned_start, order.due_date
        created = order.planned_start - timedelta(days=25)

    manager = people[spec.manager]
    inquiry = Inquiry.objects.create(
        id=inquiry_id,
        number=spec.number,
        customer_id=_party_id(spec.customer, actor_id),
        customer_name=spec.customer,
        object_name=spec.object_name,
        template_id=template.id,
        product_name=template.name,
        quantity=Decimal(spec.quantity),
        due_date=due,
        manager=manager,
        stage=spec.stage,
        order_id=order_id,
    )
    if spec.with_calc:
        replace_calculation(inquiry, template)
        if spec.drop_last_material:
            last = CalcMaterial.objects.filter(inquiry=inquiry).order_by("-sort_order").first()
            if last is not None:
                last.delete()
        if spec.one_person_ops:
            operations = list(CalcOperation.objects.filter(inquiry=inquiry).order_by("seq"))
            for index in spec.one_person_ops:
                operations[index].people = 1
            CalcOperation.objects.bulk_update(operations, ["people"])
        if planned_start is not None:
            inquiry.planned_start = planned_start
            inquiry.save(update_fields=["planned_start"])
            schedule_inquiry(inquiry)

    responsibles = {
        InquiryStage.NEW: manager,
        InquiryStage.CALC: people["Петрова Е."],
        InquiryStage.APPROVAL: manager,
    }
    passed = (
        INQUIRY_STAGE_SEQUENCE
        if launched
        else INQUIRY_STAGE_SEQUENCE[: INQUIRY_STAGE_SEQUENCE.index(spec.stage)]
    )
    InquiryStageApproval.objects.bulk_create(
        [
            InquiryStageApproval(
                inquiry=inquiry,
                stage=stage,
                responsible=responsible,
                approved_by=responsible if stage in passed else None,
                approved_at=(
                    _at(created + timedelta(days=index * 3), 15) if stage in passed else None
                ),
            )
            for index, (stage, responsible) in enumerate(responsibles.items())
        ]
    )


def _bump_counter() -> None:
    """Номера заявок демо-набора — номера прототипа (до З-0430); счётчик нумератора
    подтягивается, чтобы новая заявка не получила занятый номер."""

    numerator = Numerator.objects.get(code="sales.inquiry")
    counter, _ = NumeratorCounter.objects.get_or_create(
        numerator=numerator, period_key="", defaults={"last_value": 0}
    )
    top = max(int(spec.number.split("-")[1]) for spec in INQUIRIES)
    if counter.last_value < top:
        counter.last_value = top
        counter.save(update_fields=["last_value", "updated_at"])


def seed_demo() -> None:
    today = timezone.localdate()
    people = _employees()
    actor_id = people["Иванов А."].user_id or people["Иванов А."].id
    with transaction.atomic():
        _seed_reference(people)
        for spec in INQUIRIES:
            _seed_inquiry(spec, people, actor_id, today)
        _bump_counter()
