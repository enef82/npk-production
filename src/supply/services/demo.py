"""Демо-данные снабжения — перенос `SUPPL`, `TOOL_TPL` и `seedProc` прототипа
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.4, §3.8).

- Поставщики прототипа и типовая оснастка участков — по кодам участков `production`.
- Потребность каждого демо-заказа в работе — теми же построителями, что и обработчик
  `production.order_launched` (`services.lines.material_drafts` / `tool_drafts`), и
  продвинутая по статусам по правилам `seedProc`: материалы к выполненной снабженческой
  операции приняты на склад (и выданы, если заказ уже в изготовлении), к идущей —
  заказаны (каждая четвёртая — с поставкой позже потребности), к ожидающей — заказаны
  или ждут заказа; мотор-редуктор З-0399 ещё не заказан; оснастка к начатым
  операциям выдана в цех.
- Заявка «на склад / ТО» — запчасти к ТО станков.

Вместо `rnd()` прототипа — детерминированный выбор по номеру строки. Журнал заказа
демо-строкам не пишется (как и в прототипе: `seedProc` пишет только историю строки).
Идемпотентно: заказ, у которого уже есть строки, пропускается.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from uuid import UUID, uuid5

from django.db import transaction
from django.utils import timezone

from src.core.common.scheduling import add_working_days
from src.core.numbering import facade as numbering
from src.core.org.models import Employee
from src.production import facade as production
from src.supply.models import (
    LineCategory,
    LineKind,
    LineStatus,
    PurchaseLine,
    PurchaseLineHistory,
    Supplier,
    ToolTemplate,
)
from src.supply.services.lines import (
    DEFAULT_STORAGE,
    PURCHASE_ORDER_NUMERATOR,
    REQUISITION_NUMERATOR,
    LineDTO,
    fmt,
    material_drafts,
    tool_drafts,
)

DEMO_NAMESPACE = UUID("5f0c3a52-7d4e-5b8a-9e61-2c4b1d7a9f30")

SUPPLIERS = (
    "ООО «Уралметаллсервис»",
    "ООО «ЭлектроКомплект-Урал»",
    "ООО «ПриводТехника»",
    "ООО «ИнструментЦентр»",
    "ООО «ТехГаз»",
    "ООО «ЛакКраска-Урал»",
    "ООО «Подшипник-Снаб»",
    "ООО «АвтоматикаСнаб»",
)

T, C, F = (LineCategory.TOOL, LineCategory.CONSUMABLE, LineCategory.FIXTURE)
# Код участка → (категория, наименование, количество, ед., цена) — `TOOL_TPL`.
TOOL_TEMPLATES: dict[str, tuple[tuple[LineCategory, str, str, str, int], ...]] = {
    "list": (
        (T, "Сопло лазерное 1,5 мм", "5", "шт", 450),
        (C, "Защитное стекло линзы", "2", "шт", 1800),
        (C, "Азот газообразный, баллон 40 л", "4", "бал", 1900),
    ),
    "meh": (
        (T, "Пластины токарные CNMG 120408", "20", "шт", 420),
        (T, "Фреза концевая твердосплавная Ø12", "2", "шт", 3900),
        (C, "СОЖ, концентрат", "10", "л", 380),
        (F, "Кулачки мягкие для патрона Ø200", "1", "компл", 8500),
    ),
    "svar": (
        (C, "Проволока сварочная Св-08Г2С Ø1,2", "15", "кг", 260),
        (C, "Газ смесь Ar/CO2, баллон 40 л", "3", "бал", 3200),
        (F, "Кондуктор сборки рамы", "1", "шт", 24000),
    ),
    "pok": (
        (C, "Краска порошковая RAL 7035", "5", "кг", 690),
        (C, "Фильтры камеры окраски", "2", "шт", 2100),
    ),
    "sb": (
        (C, "DIN-рейка, кабель-канал", "1", "компл", 2500),
        (C, "Стяжки, маркировка", "1", "компл", 1200),
    ),
    "em": (
        (C, "Наконечники НШВИ, термоусадка", "1", "компл", 1800),
        (T, "Кримпер для НШВИ", "1", "шт", 4200),
    ),
    "izg": (
        (C, "Смазка, герметик", "1", "компл", 1500),
        (F, "Приспособление для сборки узла", "1", "шт", 12000),
    ),
    "otk": ((T, "Калибр, шаблон контроля", "1", "шт", 3500),),
}

# Заявка на общие нужды — запчасти к ТО: (наименование, категория, кол-во, ед., цена).
MAINTENANCE_LINES = (
    ("Фильтр чиллера лазерного станка", C, "2", "шт", 4800),
    ("Ролики направляющие ленточнопильного станка", F, "2", "шт", 6200),
    ("Масло компрессорное, 20 л", C, "1", "кан", 9800),
)

PERSONNEL = {
    "Гусев И.": "0000110",
    "Морозов Д.": "0000120",
    "Кузнецов В.": "0000204",
    "Шилова Л.": "0000205",
}
LATE_ORDER = "З-0399"


def _supplier_for(name: str, category: str, suppliers: dict[str, Supplier]) -> Supplier:
    """`supFor` прототипа — поставщик по наименованию позиции."""

    text = name.lower()
    if any(word in text for word in ("лист", "прокат", "металл", "шин", "кругл")):
        key = SUPPLIERS[0]
    elif any(word in text for word in ("редуктор", "двигат")):
        key = SUPPLIERS[2]
    elif "подшип" in text:
        key = SUPPLIERS[6]
    elif any(word in text for word in ("газ", "азот")):
        key = SUPPLIERS[4]
    elif any(word in text for word in ("краск", "абразив", "фильтр")):
        key = SUPPLIERS[5]
    elif category in (LineCategory.TOOL, LineCategory.FIXTURE):
        key = SUPPLIERS[3]
    elif any(word in text for word in ("плк", "терминал", "зву", "модул")):
        key = SUPPLIERS[7]
    else:
        key = SUPPLIERS[1]
    return suppliers[key]


def _at(day: date, hour: int) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, 0)))


class _Builder:
    def __init__(
        self,
        people: dict[str, Employee],
        suppliers: dict[str, Supplier],
        centers: dict[UUID, str],
        today: date,
    ) -> None:
        self.people = people
        self.suppliers = suppliers
        self.centers = centers
        self.today = today
        self.lines: list[PurchaseLine] = []
        self.history: list[PurchaseLineHistory] = []

    def log(self, line: PurchaseLine, text: str, who: Employee, at: datetime) -> None:
        self.history.append(PurchaseLineHistory(line=line, author=who, text=text, created_at=at))

    def sent(
        self,
        order_id: UUID | None,
        data: LineDTO,
        number: str,
        who: Employee,
        at: datetime,
        note: str = "",
    ) -> dict[str, object]:
        """Поля строки, переданной в закупку; статус и остальное дописывают шаги."""

        return {
            "order_id": order_id,
            "operation_id": data.operation_id,
            "kind": data.kind,
            "category": data.category,
            "name": data.name,
            "quantity": data.quantity,
            "unit": data.unit,
            "price": data.price,
            "need_date": data.need_date,
            "requisition_no": number,
            "sent_at": at,
            "sent_by": who,
            "created_by": who,
            "status": LineStatus.SENT,
            "_log": [(f"Заявка {number} передана в закупку{note}", who, at)],
        }

    def ordered(self, fields: dict[str, object], eta: date, at: datetime) -> None:
        supplier = _supplier_for(str(fields["name"]), str(fields["category"]), self.suppliers)
        po = numbering.issue_number(PURCHASE_ORDER_NUMERATOR)
        fields.update(status=LineStatus.ORDERED, supplier=supplier, po_number=po, eta=eta)
        self._note(fields, f"Заказано у {supplier.name}, {po}, срок {fmt(eta)}", "Кузнецов В.", at)

    def received(self, fields: dict[str, object], day: date) -> None:
        day = min(day, self.today)
        fields.update(
            status=LineStatus.RECEIVED,
            received_at=day,
            received_qty=fields["quantity"],
            storage_place=DEFAULT_STORAGE,
        )
        self._note(fields, "Принято на склад", "Шилова Л.", _at(day, 15))

    def reserved(self, fields: dict[str, object], day: date) -> None:
        day = min(day, self.today)
        fields.update(status=LineStatus.RESERVED, received_at=day, storage_place=DEFAULT_STORAGE)
        self._note(fields, "Резерв со склада — закупка не требуется", "Шилова Л.", _at(day, 14))

    def issued(self, fields: dict[str, object], day: date, center: str) -> None:
        day = min(day, self.today)
        recipient = self.people["Гусев И."]
        fields.update(status=LineStatus.ISSUED, issued_at=day, issued_to=recipient)
        self._note(
            fields,
            f"Передано в производство: {center}, получил {recipient.full_name}",
            "Шилова Л.",
            _at(day, 9),
        )

    def _note(self, fields: dict[str, object], text: str, who: str, at: datetime) -> None:
        log = fields["_log"]
        assert isinstance(log, list)
        log.append((text, self.people[who], at))

    def add(self, fields: dict[str, object]) -> None:
        log = fields.pop("_log")
        assert isinstance(log, list)
        line = PurchaseLine(**fields)
        self.lines.append(line)
        for text, who, at in log:
            self.log(line, text, who, at)


def _seed_reference(centers: dict[str, UUID]) -> dict[str, Supplier]:
    suppliers = {name: Supplier.objects.get_or_create(name=name)[0] for name in SUPPLIERS}
    for code, rows in TOOL_TEMPLATES.items():
        if code not in centers:
            continue
        for order, (category, name, qty, unit, price) in enumerate(rows, start=1):
            ToolTemplate.objects.get_or_create(
                work_center_id=centers[code],
                name=name,
                defaults={
                    "category": category,
                    "quantity": Decimal(qty),
                    "unit": unit,
                    "price": Decimal(price),
                    "order": order,
                },
            )
    return suppliers


def _seed_order(builder: _Builder, order: production.OrderBrief, manager: Employee) -> None:
    today = builder.today
    operations = {op.id: op for op in production.list_order_operations(order.id)}
    sent_day = order.planned_start if order.planned_start < today else today - timedelta(days=1)
    sent_at = _at(sent_day, 10)
    ordered_at = _at(min(today, sent_day + timedelta(days=2)), 11)
    in_production = order.stage in (production.OrderStage.PROD, production.OrderStage.QC)
    late_order = order.id == uuid5(DEMO_NAMESPACE, f"order/{LATE_ORDER}")

    number = numbering.issue_number(REQUISITION_NUMERATOR)
    for i, data in enumerate(material_drafts(order)):
        fields = builder.sent(order.id, data, number, manager, sent_at)
        op = operations.get(data.operation_id) if data.operation_id else None
        if late_order and "редуктор" in data.name.lower():
            pass  # критический путь З-0399: мотор-редуктор ещё не заказан
        elif op is None or op.status == production.OperationStatus.DONE:
            eta = (op.planned_finish if op else None) or today
            builder.ordered(fields, eta, ordered_at)
            builder.received(fields, eta)
            if in_production:
                builder.issued(fields, add_working_days(eta, 1), "производство")
        elif op.status == production.OperationStatus.WORK:
            shift = 5 if i % 4 == 0 else -2
            builder.ordered(fields, data.need_date + timedelta(days=shift), ordered_at)
        elif order.stage != production.OrderStage.LAUNCH and i % 2 == 0:
            builder.ordered(fields, data.need_date - timedelta(days=1), ordered_at)
        builder.add(fields)

    if order.stage == production.OrderStage.LAUNCH:
        return
    foreman = builder.people["Гусев И."]
    number = numbering.issue_number(REQUISITION_NUMERATOR)
    for i, data in enumerate(tool_drafts(order)):
        fields = builder.sent(order.id, data, number, foreman, sent_at)
        op = operations[data.operation_id] if data.operation_id else None
        if op is not None and op.status != production.OperationStatus.WAIT:
            start = op.planned_start or today
            if i % 5 < 2:
                builder.reserved(fields, start - timedelta(days=3))
            else:
                builder.ordered(fields, start - timedelta(days=3), ordered_at)
                builder.received(fields, start - timedelta(days=3))
            builder.issued(fields, start, builder.centers.get(op.work_center_id, ""))
        elif i % 3 == 0:
            builder.ordered(fields, data.need_date - timedelta(days=2), ordered_at)
        builder.add(fields)


def _seed_maintenance(builder: _Builder) -> None:
    today = builder.today
    foreman = builder.people["Гусев И."]
    number = numbering.issue_number(REQUISITION_NUMERATOR)
    at = _at(today, 9)
    for i, (name, category, qty, unit, price) in enumerate(MAINTENANCE_LINES):
        data = LineDTO(
            kind=LineKind.TOOL,
            category=category,
            name=name,
            quantity=Decimal(qty),
            unit=unit,
            price=Decimal(price),
            need_date=today + timedelta(days=1 if i == 1 else 6),
        )
        fields = builder.sent(None, data, number, foreman, at, " (ТО и ремонт)")
        if i == 1:
            builder.ordered(fields, today + timedelta(days=3), at)
        builder.add(fields)


def seed_demo() -> None:
    today = timezone.localdate()
    work_centers = production.list_work_centers()
    centers = {center.code: center.id for center in work_centers}
    people = {
        name: e
        for e in Employee.objects.filter(personnel_number__in=PERSONNEL.values())
        for name, tab in PERSONNEL.items()
        if e.personnel_number == tab
    }
    if len(people) < len(PERSONNEL):
        return
    with transaction.atomic():
        suppliers = _seed_reference(centers)
        orders = sorted(production.list_active_orders(), key=lambda o: o.number)
        busy = set(
            PurchaseLine.objects.filter(order_id__in=[o.id for o in orders]).values_list(
                "order_id", flat=True
            )
        )
        builder = _Builder(people, suppliers, {c.id: c.name for c in work_centers}, today)
        managers = {e.id: e for e in Employee.objects.filter(id__in={o.manager_id for o in orders})}
        for order in orders:
            if order.id not in busy:
                _seed_order(builder, order, managers[order.manager_id])
        if not PurchaseLine.objects.filter(order_id__isnull=True).exists():
            _seed_maintenance(builder)
        PurchaseLine.objects.bulk_create(builder.lines)
        PurchaseLineHistory.objects.bulk_create(builder.history)
