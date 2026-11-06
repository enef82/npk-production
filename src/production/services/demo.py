"""Демо-данные «Производства» — перенос `seed()` прототипа
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.8, последний абзац).

Справочники (12 участков, 8 шаблонов), ответственные этапов и 14 производственных
заказов на разных этапах: операции выполнены, начаты или ждут по датам относительно
сегодняшнего дня, освоение разнесено по рабочим дням, визы и журнал проставлены.
Детерминированно: ни одного случайного числа.

Связь с `sales.seed_demo` без обращения к чужим моделям — по детерминированным
идентификаторам: заказ по заявке «З-0402» получает `id = uuid5(DEMO_NAMESPACE,
"order/З-0402")` и `inquiry_id = uuid5(DEMO_NAMESPACE, "inquiry/З-0402")`; `sales`
заводит заявку с тем же `id` и тем же `order_id`. Заказчики — `Party` ядра: кто первым
встретил имя, тот и создал, второй находит по точному наименованию.

Сотрудники заводятся командой `seed_demo` (`analytics`) до вызова; здесь они ищутся по
табельным номерам прототипа (`EMP`, `PEOPLE`).

Сумма заказа (`contract_total`) считается по формуле `calcTotals` прототипа со
стандартными 25 / 20 / 22 % — той же, что `sales.calculations`, — потому что заказ
демо-набора создаётся раньше заявки; у запущенной через интерфейс заявки сумму передаёт
`sales` в `LaunchData`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID, uuid5

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import transaction
from django.utils import timezone

from src.core.common.exceptions import ConflictError
from src.core.common.scheduling import add_working_days, work_index
from src.core.documents import facade as documents
from src.core.identity import facade as identity
from src.core.identity.models import Party
from src.core.numbering.models import Numerator, NumeratorCounter
from src.core.org.models import Employee
from src.production.models import (
    ORDER_STAGE_SEQUENCE,
    DocumentRelease,
    JournalKind,
    Operation,
    OperationDependency,
    OperationEarning,
    OperationStatus,
    OrderJournalEntry,
    OrderStage,
    OrderStageApproval,
    ProductionOrder,
    ProductionSettings,
    ProductTemplate,
    TemplateMaterial,
    TemplateOperation,
    TemplateOperationDependency,
    WorkCenter,
    WorkPhase,
)
from src.production.planning import duration_of, finish_of
from src.production.selectors import OPERATION_ENTITY, ORDER_ENTITY, derived_stage
from src.production.services.common import reschedule

DEMO_NAMESPACE = UUID("5f0c3a52-7d4e-5b8a-9e61-2c4b1d7a9f30")

# Табельные номера ролевых персонажей прототипа — та же таблица в команде `seed_demo`.
PERSONNEL = {
    "Белов С.": "0000101",
    "Сидоров К.": "0000102",
    "Лебедев П.": "0000103",
    "Гусев И.": "0000110",
    "Морозов Д.": "0000120",
    "Орлова Н.": "0000130",
    "Иванов А.": "0000201",
    "Зайцева М.": "0000202",
    "Петрова Е.": "0000203",
    "Кузнецов В.": "0000204",
    "Шилова Л.": "0000205",
}

# (код, краткое, наименование, ставка, мощность, ответственный, фаза, снабжение) — `WC`.
WORK_CENTERS = (
    ("kb", "КО", "Конструкторский отдел", 1800, 1, "Белов С.", WorkPhase.PREP, False),
    (
        "tp",
        "ТП",
        "Технологическая подготовка, УП ЧПУ",
        1700,
        1,
        "Сидоров К.",
        WorkPhase.PREP,
        False,
    ),
    ("snab", "Снаб", "Снабжение (закупка, кооперация)", 0, 0, "Кузнецов В.", WorkPhase.PREP, True),
    (
        "list",
        "Лист",
        "Листовая обработка (лазер, гибка)",
        1500,
        1,
        "Гусев И.",
        WorkPhase.PROD,
        False,
    ),
    (
        "meh",
        "Мех",
        "Мехобработка (токарная, фрезерная ЧПУ)",
        1700,
        2,
        "Гусев И.",
        WorkPhase.PROD,
        False,
    ),
    ("svar", "Свар", "Сварочный участок", 1400, 2, "Гусев И.", WorkPhase.PROD, False),
    ("pok", "Покр", "Покрасочный участок", 1100, 1, "Морозов Д.", WorkPhase.PROD, False),
    ("izg", "СбОб", "Сборка оборудования", 1400, 2, "Морозов Д.", WorkPhase.PROD, False),
    ("sb", "СбШк", "Сборка шкафов", 1300, 2, "Морозов Д.", WorkPhase.PROD, False),
    ("em", "ЭМ", "Электромонтаж", 1400, 3, "Морозов Д.", WorkPhase.PROD, False),
    ("prog", "Прог", "Программирование ПЛК / РЗА", 1900, 1, "Лебедев П.", WorkPhase.PROD, False),
    ("otk", "ОТК", "ОТК и испытания", 1500, 1, "Орлова Н.", WorkPhase.QC, False),
)

D = Decimal


# `TPL` прототипа.
@dataclass(frozen=True)
class TemplateSpec:
    name: str
    # (имя, количество на единицу, цена)
    mat: list[tuple[str, int, int]]
    # (имя, участок, н-ч или дни, зависит от количества, предшественники, исполнителей)
    ops: list[tuple[str, str, str, bool, list[int], int]]


TEMPLATES: dict[str, TemplateSpec] = {
    "ШУ": TemplateSpec(
        name="Шкаф управления АСУ ТП",
        mat=[
            ("Корпус напольный 1800×800×600 IP54", 1, 68000),
            ("ПЛК с модулями ввода-вывода", 1, 240000),
            ("Коммутационная аппаратура", 1, 95000),
            ("Клеммы, провод, маркировка", 1, 38000),
        ],
        ops=[
            ("Разработка КД на шкаф", "kb", "24", False, [], 1),
            ("Закупка комплектующих", "snab", "15", False, [0], 1),
            ("Подготовка программ раскроя панелей", "tp", "4", False, [0], 1),
            ("Сборка монтажной панели", "sb", "16", True, [1, 2], 1),
            ("Электромонтаж", "em", "40", True, [3], 2),
            ("Разработка ПО ПЛК", "prog", "32", False, [0], 1),
            ("Загрузка и отладка ПО", "prog", "8", True, [4, 5], 1),
            ("Испытания и ОТК", "otk", "8", True, [6], 1),
        ],
    ),
    "НКУ": TemplateSpec(
        name="НКУ 0,4 кВ",
        mat=[
            ("Аппаратура: вводные и секционные автоматы", 1, 310000),
            ("Лист оцинкованный 2 мм", 1, 42000),
            ("Шинная система медь", 1, 74000),
            ("Приборы учёта и измерения", 1, 46000),
        ],
        ops=[
            ("Разработка КД", "kb", "20", False, [], 1),
            ("Закупка аппаратуры", "snab", "20", False, [0], 1),
            ("Закупка листового металла", "snab", "5", False, [0], 1),
            ("УП лазерной резки и гибки", "tp", "6", False, [0], 1),
            ("Лазерная резка и гибка", "list", "12", True, [2, 3], 1),
            ("Сварка каркаса", "svar", "8", True, [4], 1),
            ("Порошковая покраска", "pok", "6", True, [5], 1),
            ("Сборка и ошиновка", "sb", "28", True, [1, 6], 2),
            ("Электромонтаж вторичных цепей", "em", "24", True, [7], 2),
            ("Испытания и ОТК", "otk", "10", True, [8], 1),
        ],
    ),
    "ВРУ": TemplateSpec(
        name="ВРУ / ЩР 0,4 кВ",
        mat=[
            ("Корпус ВРУ", 1, 38000),
            ("Аппаратура защиты", 1, 86000),
            ("Шины, провод, клеммы", 1, 21000),
        ],
        ops=[
            ("Разработка КД", "kb", "8", False, [], 1),
            ("Закупка аппаратуры", "snab", "10", False, [0], 1),
            ("Сборка", "sb", "10", True, [1], 1),
            ("Электромонтаж", "em", "14", True, [2], 2),
            ("Испытания и ОТК", "otk", "4", True, [3], 1),
        ],
    ),
    "ШОТ": TemplateSpec(
        name="Шкаф оперативного тока",
        mat=[
            ("Корпус 2000×800×600", 1, 74000),
            ("Зарядно-выпрямительное устройство", 1, 280000),
            ("Аккумуляторная батарея", 1, 190000),
            ("Аппаратура распределения", 1, 64000),
        ],
        ops=[
            ("Разработка КД", "kb", "16", False, [], 1),
            ("Закупка ЗВУ и АКБ", "snab", "25", False, [0], 1),
            ("Закупка корпуса и аппаратуры", "snab", "10", False, [0], 1),
            ("Сборка", "sb", "18", True, [2], 1),
            ("Электромонтаж", "em", "26", True, [3], 2),
            ("Установка ЗВУ и АКБ", "sb", "6", True, [1, 4], 1),
            ("Испытания и ОТК", "otk", "12", True, [5], 1),
        ],
    ),
    "РЗА": TemplateSpec(
        name="Шкаф РЗА / ПА",
        mat=[
            ("Корпус релейного шкафа", 1, 82000),
            ("Терминалы РЗА", 1, 520000),
            ("Испытательные блоки, клеммы", 1, 48000),
        ],
        ops=[
            ("Разработка КД", "kb", "28", False, [], 1),
            ("Закупка терминалов РЗА", "snab", "30", False, [0], 1),
            ("Закупка корпуса и аппаратуры", "snab", "10", False, [0], 1),
            ("Сборка", "sb", "14", True, [2], 1),
            ("Электромонтаж", "em", "36", True, [3], 2),
            ("Параметрирование терминалов", "prog", "20", True, [1], 1),
            ("Установка терминалов и испытания", "otk", "14", True, [4, 5], 1),
        ],
    ),
    "МЕХ": TemplateSpec(
        name="Детали мехобработки по чертежам",
        mat=[
            ("Прокат круглый 40Х", 1, 1800),
            ("Прокат листовой 09Г2С", 1, 900),
            ("Термообработка (кооперация)", 1, 650),
            ("Инструмент и расходники", 1, 400),
        ],
        ops=[
            ("Анализ КД заказчика, техпроцесс", "tp", "6", False, [], 1),
            ("Разработка УП ЧПУ (токарная, фрезерная)", "tp", "10", False, [0], 1),
            ("Закупка проката", "snab", "7", False, [0], 1),
            ("Заготовительная резка", "meh", "0.5", True, [2], 1),
            ("Токарная обработка ЧПУ", "meh", "1.5", True, [1, 3], 2),
            ("Фрезерная обработка ЧПУ", "meh", "2", True, [4], 2),
            ("Термообработка (кооперация)", "snab", "5", False, [5], 1),
            ("Слесарная доработка", "izg", "0.5", True, [6], 1),
            ("Контроль ОТК", "otk", "0.4", True, [7], 1),
        ],
    ),
    "ЛИСТ": TemplateSpec(
        name="Корпуса и листовые металлоконструкции",
        mat=[
            ("Лист холоднокатаный 2 мм", 1, 4200),
            ("Крепёж, петли, замки", 1, 1800),
            ("Порошковая краска", 1, 600),
        ],
        ops=[
            ("Разработка КД", "kb", "16", False, [], 1),
            ("УП раскроя и гибки", "tp", "6", False, [0], 1),
            ("Закупка листа", "snab", "7", False, [0], 1),
            ("Лазерная резка", "list", "1.5", True, [1, 2], 1),
            ("Гибка", "list", "1", True, [3], 1),
            ("Сварка", "svar", "2", True, [4], 1),
            ("Порошковая покраска", "pok", "0.8", True, [5], 1),
            ("Сборка, установка фурнитуры", "izg", "1", True, [6], 1),
            ("Контроль ОТК", "otk", "0.3", True, [7], 1),
        ],
    ),
    "ОБОР": TemplateSpec(
        name="Решётка-дробилка для КНС",
        mat=[
            ("Прокат и лист нержавеющий", 1, 210000),
            ("Мотор-редуктор", 1, 380000),
            ("Подшипниковые узлы", 1, 64000),
            ("Шкаф управления (покупной)", 1, 145000),
            ("Крепёж, уплотнения", 1, 28000),
        ],
        ops=[
            ("Разработка КД", "kb", "80", False, [], 1),
            ("Техпроцесс и УП ЧПУ", "tp", "24", False, [0], 1),
            ("Закупка проката", "snab", "10", False, [0], 1),
            ("Закупка мотор-редуктора", "snab", "35", False, [0], 1),
            ("Листовая обработка рамы и корпуса", "list", "30", True, [1, 2], 1),
            ("Мехобработка валов и режущих дисков", "meh", "48", True, [1, 2], 2),
            ("Сварка рамы", "svar", "36", True, [4], 2),
            ("Покраска", "pok", "12", True, [6], 1),
            ("Сборка оборудования", "izg", "48", True, [3, 5, 7], 2),
            ("Обкатка и ОТК", "otk", "16", True, [8], 1),
        ],
    ),
}

# Стандартные проценты калькуляции прототипа (накладные, наценка, НДС).
_OVERHEAD, _MARGIN, _VAT = D(25), D(20), D(22)


@dataclass(frozen=True)
class DemoOrder:
    """Заказ демо-набора: заявка, заказчик, изделие, срок и сдвиг запуска."""

    inquiry_number: str
    order_seq: str
    customer: str
    object_name: str
    template: str
    quantity: int
    manager: str
    # Запуск: рабочих дней от сегодня. `due_days` — календарных дней от сегодня;
    # `None` — срок = плановое окончание + `slack` календарных дней (`mkOrd`).
    start_offset: int
    due_days: int | None = None
    slack: int = 0
    stage: OrderStage | None = None
    # Индексы операций, у которых исполнителей меньше шаблона (`s.calc.ops[4].ppl=1`).
    one_person_ops: tuple[int, ...] = ()
    # План заканчивается завтрашним рабочим днём (заказ «З-0381», `k`).
    finish_tomorrow: bool = False


ORDERS = (
    DemoOrder(
        "З-0402",
        "0142",
        "АО «Святогор»",
        "ПС 110 кВ «Обогатительная»",
        "РЗА",
        2,
        "Иванов А.",
        3,
        due_days=72,
        stage=OrderStage.LAUNCH,
    ),
    DemoOrder(
        "З-0399",
        "0141",
        "ООО «Водоканал-НТ»",
        "КНС-12, решётка-дробилка",
        "ОБОР",
        1,
        "Зайцева М.",
        -6,
        due_days=74,
    ),
    DemoOrder(
        "З-0396",
        "0139",
        "ООО «УГМК-Холдинг»",
        "Котельная промплощадки",
        "ВРУ",
        4,
        "Иванов А.",
        -13,
        due_days=14,
    ),
    DemoOrder(
        "З-0393",
        "0137",
        "АО «Уралмашзавод»",
        "Валы приводные, 20 шт.",
        "МЕХ",
        20,
        "Зайцева М.",
        -14,
        due_days=20,
    ),
    DemoOrder(
        "З-0390",
        "0135",
        "АО «Уралэлектромедь»",
        "Цех электролиза, вентиляция",
        "ШУ",
        3,
        "Иванов А.",
        -28,
        due_days=12,
        one_person_ops=(4,),
    ),
    DemoOrder(
        "З-0381",
        "0131",
        "ООО «Газпром трансгаз Екатеринбург»",
        "ГРС «Северная»",
        "НКУ",
        1,
        "Зайцева М.",
        0,
        due_days=5,
        finish_tomorrow=True,
    ),
    DemoOrder("З-0377", "0127", "АО «ЕЭСК»", "РП-7", "ВРУ", 2, "Иванов А.", -30, due_days=-2),
    DemoOrder(
        "З-0384",
        "0132",
        "АО «Камышловский завод „Урализолятор“»",
        "Сушильная камера, автоматика",
        "ШУ",
        4,
        "Иванов А.",
        -12,
        slack=9,
    ),
    DemoOrder(
        "З-0386",
        "0134",
        "ООО «Водоканал Асбест»",
        "КНС-5, решётка-дробилка",
        "ОБОР",
        1,
        "Зайцева М.",
        -24,
        slack=12,
    ),
    DemoOrder(
        "З-0388",
        "0136",
        "АО «Уралхиммаш»",
        "Оси и втулки, 40 шт.",
        "МЕХ",
        40,
        "Зайцева М.",
        -6,
        slack=6,
    ),
    DemoOrder(
        "З-0392",
        "0138",
        "ООО «Элмаш»",
        "Корпуса пультов, 30 шт.",
        "ЛИСТ",
        30,
        "Иванов А.",
        -9,
        slack=8,
    ),
    DemoOrder(
        "З-0395", "0140", "АО «ЕЭнС»", "ТП-31, НКУ 0,4 кВ", "НКУ", 3, "Иванов А.", -4, slack=15
    ),
    DemoOrder(
        "З-0397",
        "0144",
        "МУП «Водоканал» г. Ревда",
        "Очистные сооружения, 2 решётки",
        "ОБОР",
        2,
        "Зайцева М.",
        -3,
        slack=14,
    ),
    DemoOrder(
        "З-0400",
        "0145",
        "ОАО «МРСК Урала»",
        "ПС 35 кВ «Садовая»",
        "РЗА",
        1,
        "Иванов А.",
        2,
        slack=20,
        stage=OrderStage.LAUNCH,
    ),
)

# Документы заказа: (вид, имя файла, индекс операции или None, утверждён) — `docs()`.
DOCUMENTS: dict[str, tuple[tuple[str, str, int | None, bool], ...]] = {
    "З-0402": (("production.kd", "РЗА — КД комплект изм.0.pdf", 0, True),),
    "З-0399": (
        ("production.tz", "Опросный лист решётки.pdf", None, True),
        ("production.drawing", "Рама сварная (эскиз).dxf", 0, False),
    ),
    "З-0396": (
        ("production.kd", "ВРУ — КД изм.1.pdf", 0, True),
        ("production.specification", "Спецификация аппаратуры.xlsx", 1, True),
    ),
    "З-0393": (
        ("production.drawing", "Вал приводной УМ-204.03.pdf", 0, True),
        ("production.process", "ТП вал УМ-204.pdf", 0, True),
        ("production.cnc", "VAL_204_T1.nc", 1, True),
        ("production.cnc", "VAL_204_F2.nc", 1, True),
    ),
    "З-0390": (
        ("production.kd", "ШУ вентиляции — КД.pdf", 0, True),
        ("production.drawing", "Монтажная панель.dwg", 0, True),
    ),
    "З-0381": (
        ("production.kd", "НКУ ГРС — КД.pdf", 0, True),
        ("production.cnc", "NKU_laser.nc", 3, True),
    ),
}

# Комментарии: (номер заявки, индекс операции, автор, час, текст) — сегодня.
COMMENTS = (
    (
        "З-0399",
        3,
        "Кузнецов В.",
        10,
        "Запрос по мотор-редуктору отправлен трём поставщикам. Срок поставки 6–7 недель — "
        "это критический путь.",
    ),
    (
        "З-0390",
        4,
        "Морозов Д.",
        9,
        "На электромонтаже один монтажник — второй на больничном. Срок под угрозой.",
    ),
)

_HOURS = D("0.01")
_QTY = D("0.001")


def demo_inquiry_id(number: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"inquiry/{number}")


def demo_order_id(number: str) -> UUID:
    return uuid5(DEMO_NAMESPACE, f"order/{number}")


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


def _seed_work_centers(people: dict[str, Employee]) -> dict[str, WorkCenter]:
    centers = {}
    for index, (code, short, name, rate, cap, resp, phase, supply) in enumerate(WORK_CENTERS):
        center, _ = WorkCenter.objects.get_or_create(
            code=code,
            defaults={
                "short_name": short,
                "name": name,
                "hourly_rate": D(rate),
                "capacity": cap,
                "responsible": people[resp],
                "phase": phase,
                "is_supply": supply,
                "sort_order": index,
            },
        )
        centers[code] = center
    return centers


def _seed_templates(centers: dict[str, WorkCenter]) -> None:
    for code, spec in TEMPLATES.items():
        template, created = ProductTemplate.objects.get_or_create(
            code=code, defaults={"name": spec.name}
        )
        if not created:
            continue
        TemplateMaterial.objects.bulk_create(
            [
                TemplateMaterial(
                    template=template, name=name, qty_per_unit=D(qty), price=D(price), sort_order=i
                )
                for i, (name, qty, price) in enumerate(spec.mat)
            ]
        )
        ops = TemplateOperation.objects.bulk_create(
            [
                TemplateOperation(
                    template=template,
                    seq=(i + 1) * 10,
                    name=name,
                    work_center=centers[wc],
                    hours=D(hours),
                    scales_with_qty=scales,
                    people=people,
                    sort_order=i,
                )
                for i, (name, wc, hours, scales, _, people) in enumerate(spec.ops)
            ]
        )
        TemplateOperationDependency.objects.bulk_create(
            [
                TemplateOperationDependency(predecessor=ops[pred], successor=ops[i])
                for i, (_, _, _, _, preds, _) in enumerate(spec.ops)
                for pred in preds
            ]
        )


def _seed_settings(people: dict[str, Employee]) -> None:
    settings, _ = ProductionSettings.objects.get_or_create()
    if settings.launch_responsible_id is None:
        settings.launch_responsible = people["Морозов Д."]
        settings.prep_responsible = people["Сидоров К."]
        settings.prod_responsible = people["Морозов Д."]
        settings.qc_responsible = people["Орлова Н."]
        settings.save()


def _party_id(name: str, actor_id: UUID) -> UUID:
    existing = Party.objects.filter(short_name=name).first()
    if existing is not None:
        return existing.id
    party = identity.create_party(
        identity.PartyCreateDTO(legal_name=name, short_name=name), actor_id=actor_id, force=True
    )
    return party.id


def _round1(value: Decimal) -> Decimal:
    return value.quantize(D("0.1"), ROUND_HALF_UP)


def _template_lines(
    spec: TemplateSpec, quantity: int
) -> tuple[list[tuple[str, Decimal, Decimal]], list[tuple[str, str, Decimal, int, list[int]]]]:
    qty = D(quantity)
    materials = [(name, (D(q) * qty).quantize(_QTY), D(price)) for name, q, price in spec.mat]
    operations = [
        (name, wc, (D(hours) * qty).quantize(_HOURS) if scales else D(hours), people, preds)
        for name, wc, hours, scales, preds, people in spec.ops
    ]
    return materials, operations


def _totals(
    materials: list[tuple[str, Decimal, Decimal]],
    operations: list[tuple[str, str, Decimal, int, list[int]]],
    centers: dict[str, WorkCenter],
) -> tuple[Decimal, Decimal]:
    mat = sum((q * p for _, q, p in materials), D(0))
    labor = sum(
        (h * centers[wc].hourly_rate for _, wc, h, _, _ in operations if not centers[wc].is_supply),
        D(0),
    )
    cost = mat + labor + labor * _OVERHEAD / 100
    price = cost * (1 + _MARGIN / 100)
    total = price + price * _VAT / 100
    return total.quantize(D("0.0001")), labor.quantize(D("0.0001"))


def _working_days(start: date, end: date) -> list[date]:
    days = []
    day = start
    while day <= end:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


def _spread_earnings(operation: Operation, start: date, end: date, fraction: Decimal) -> None:
    """`spreadEarn` прототипа: освоение поровну по рабочим дням; остаток копеек — на
    последний день, чтобы сумма была ровно `hours × fraction`."""

    if operation.work_center.is_supply:
        return
    days = _working_days(start, end)
    if not days:
        return
    total = (operation.hours * fraction).quantize(_HOURS, ROUND_HALF_UP)
    per = (total / len(days)).quantize(_HOURS, ROUND_HALF_UP)
    rows = [OperationEarning(operation=operation, date=day, hours=per) for day in days[:-1]]
    rows.append(OperationEarning(operation=operation, date=days[-1], hours=total - per * len(rows)))
    OperationEarning.objects.bulk_create([row for row in rows if row.hours])


def _seed_documents(
    order: ProductionOrder,
    operations: list[Operation],
    people: dict[str, Employee],
    start: date,
) -> None:
    for code, name, op_index, approved in DOCUMENTS.get(order.inquiry_number, ()):
        author = (
            people["Сидоров К."]
            if code in ("production.cnc", "production.process")
            else (people["Белов С."])
        )
        uploaded_by = author.user_id or author.id
        content = f"Демо-документ: {name}\n".encode()
        stored = documents.store_upload(
            SimpleUploadedFile(name, content, content_type="application/octet-stream"),
            doc_type_code=code,
        )
        document = documents.persist_upload(stored, uploaded_by=uploaded_by)
        documents.attach_document(document.id, ORDER_ENTITY, order.id)
        operation = operations[op_index] if op_index is not None else None
        if operation is not None:
            documents.attach_document(document.id, OPERATION_ENTITY, operation.id)
        _journal(
            order,
            JournalKind.DOC,
            f"Загружен документ «{name}»",
            _at(start + timedelta(days=3), 12),
            author=author,
            operation=operation,
        )
        if approved:
            DocumentRelease.objects.create(
                document=document,
                order=order,
                operation=operation,
                approved_by=people["Сидоров К."],
                approved_at=_at(start + timedelta(days=4), 11),
            )


def _journal(
    order: ProductionOrder,
    kind: JournalKind,
    text: str,
    at: datetime,
    *,
    author: Employee | None = None,
    operation: Operation | None = None,
    stage: str = "",
) -> None:
    OrderJournalEntry.objects.create(
        order=order,
        operation=operation,
        stage=stage if stage or operation else order.stage,
        kind=kind,
        author=author,
        text=text,
        created_at=at,
    )


def _plan_length(order: ProductionOrder) -> date | None:
    operations = list(Operation.objects.filter(order=order).select_related("work_center"))
    return max((f for f in (finish_of(op) for op in operations) if f is not None), default=None)


def _seed_order(
    spec: DemoOrder,
    centers: dict[str, WorkCenter],
    people: dict[str, Employee],
    actor_id: UUID,
    today: date,
) -> None:
    number = f"ПЗ-{today.year}-{spec.order_seq}"
    if ProductionOrder.objects.filter(number=number).exists():
        return
    template_spec = TEMPLATES[spec.template]
    materials, operations_spec = _template_lines(template_spec, spec.quantity)
    contract_total, labor = _totals(materials, operations_spec, centers)
    template = ProductTemplate.objects.get(code=spec.template)
    start = add_working_days(today, spec.start_offset)
    order = ProductionOrder.objects.create(
        id=demo_order_id(spec.inquiry_number),
        number=number,
        inquiry_id=demo_inquiry_id(spec.inquiry_number),
        inquiry_number=spec.inquiry_number,
        customer_id=_party_id(spec.customer, actor_id),
        customer_name=spec.customer,
        object_name=spec.object_name,
        product_name=template_spec.name,
        template=template,
        quantity=D(spec.quantity),
        manager=people[spec.manager],
        planned_start=start,
        due_date=today,
        contract_total=contract_total,
        labor_cost_planned=labor,
    )
    operations = Operation.objects.bulk_create(
        [
            Operation(
                order=order,
                seq=(i + 1) * 10,
                name=name,
                work_center=centers[wc],
                hours=hours,
                people=1 if i in spec.one_person_ops else ppl,
                responsible=centers[wc].responsible,
            )
            for i, (name, wc, hours, ppl, _) in enumerate(operations_spec)
        ]
    )
    OperationDependency.objects.bulk_create(
        [
            OperationDependency(predecessor=operations[pred], successor=operations[i])
            for i, (_, _, _, _, preds) in enumerate(operations_spec)
            for pred in preds
        ]
    )
    reschedule(order, clamp_today=False)
    if spec.finish_tomorrow:
        # `k` прототипа: план, начатый сегодня, сдвигается так, чтобы окончание пришлось
        # на завтрашний рабочий день.
        finish = _plan_length(order)
        assert finish is not None
        length = work_index(finish) - work_index(today)
        order.planned_start = add_working_days(today, -length + 1)
        order.save(update_fields=["planned_start"])
        reschedule(order, clamp_today=False)
        start = order.planned_start
    finish = _plan_length(order)
    assert finish is not None
    order.due_date = (
        today + timedelta(days=spec.due_days)
        if spec.due_days is not None
        else finish + timedelta(days=spec.slack)
    )
    order.save(update_fields=["due_date"])

    morozov = people["Морозов Д."]
    _journal(
        order,
        JournalKind.STAGE,
        f"Создан производственный заказ {order.number}",
        _at(start, 9),
        author=morozov,
        stage=OrderStage.LAUNCH,
    )
    operations = list(
        Operation.objects.filter(order=order).select_related("work_center", "responsible")
    )
    by_seq = sorted(operations, key=lambda op: op.seq)
    yesterday = today - timedelta(days=1)
    for op in by_seq:
        assert op.planned_start is not None
        op_finish = finish_of(op)
        assert op_finish is not None
        if op_finish < today:
            Operation.objects.filter(id=op.id).update(
                status=OperationStatus.DONE,
                progress=100,
                started_at=_at(op.planned_start, 9),
                started_by=op.responsible,
                approved_at=_at(op_finish, 17),
                approved_by=op.responsible,
            )
            _spread_earnings(op, op.planned_start, op_finish, D(1))
            _journal(
                order,
                JournalKind.VISA,
                "Выполнено. Виза ответственного",
                _at(op_finish, 17),
                author=op.responsible,
                operation=op,
            )
        elif op.planned_start <= today:
            progress = 0
            if not op.work_center.is_supply:
                ratio = D(work_index(today) - work_index(op.planned_start)) / duration_of(op) * 10
                progress = min(80, int(ratio.quantize(D(1), ROUND_HALF_UP)) * 10)
            Operation.objects.filter(id=op.id).update(
                status=OperationStatus.WORK,
                progress=progress,
                started_at=_at(op.planned_start, 9),
                started_by=op.responsible,
            )
            if progress:
                _spread_earnings(
                    op, op.planned_start, max(op.planned_start, yesterday), D(progress) / 100
                )
            _journal(
                order,
                JournalKind.STATUS,
                "Операция начата",
                _at(op.planned_start, 9),
                author=op.responsible,
                operation=op,
            )

    operations = list(Operation.objects.filter(order=order).select_related("work_center"))
    stage = spec.stage or derived_stage(operations)
    ProductionOrder.objects.filter(id=order.id).update(
        stage=stage,
        shipped_at=_at(finish, 17) if stage == OrderStage.DONE else None,
    )
    order = ProductionOrder.objects.get(id=order.id)

    responsibles = {
        OrderStage.LAUNCH: morozov,
        OrderStage.PREP: people["Сидоров К."],
        OrderStage.PROD: morozov,
        OrderStage.QC: people["Орлова Н."],
        OrderStage.DONE: people[spec.manager],
    }
    created = start - timedelta(days=25)
    # Индекс этапа в общей ленте прототипа: три этапа заявки, затем этапы заказа.
    passed = ORDER_STAGE_SEQUENCE[: ORDER_STAGE_SEQUENCE.index(stage)]
    approvals = []
    for stage_value, responsible in responsibles.items():
        approved = stage_value in passed
        at = _at(created + timedelta(days=(3 + ORDER_STAGE_SEQUENCE.index(stage_value)) * 3), 15)
        approvals.append(
            OrderStageApproval(
                order=order,
                stage=stage_value,
                responsible=responsible,
                approved_by=responsible if approved else None,
                approved_at=at if approved else None,
            )
        )
        if approved:
            _journal(
                order,
                JournalKind.VISA,
                f"Этап «{stage_value.label}» завизирован",
                at,
                author=responsible,
                stage=stage_value,
            )
    OrderStageApproval.objects.bulk_create(approvals)

    _seed_documents(order, by_seq, people, start)
    for inquiry_number, op_index, author, hour, text in COMMENTS:
        if inquiry_number == spec.inquiry_number:
            _journal(
                order,
                JournalKind.COMMENT,
                text,
                _at(today, hour),
                author=people[author],
                operation=by_seq[op_index],
            )


def _bump_counter(today: date) -> None:
    """Номера заказов демо-набора — номера прототипа (до ПЗ-…-0145); счётчик нумератора
    подтягивается, чтобы следующий запуск не выдал занятый номер."""

    numerator = Numerator.objects.get(code="production.order")
    counter, _ = NumeratorCounter.objects.get_or_create(
        numerator=numerator, period_key=str(today.year), defaults={"last_value": 0}
    )
    top = max(int(spec.order_seq) for spec in ORDERS)
    if counter.last_value < top:
        counter.last_value = top
        counter.save(update_fields=["last_value", "updated_at"])


def seed_demo() -> None:
    today = timezone.localdate()
    people = _employees()
    actor_id = people["Морозов Д."].user_id or people["Морозов Д."].id
    with transaction.atomic():
        centers = _seed_work_centers(people)
        _seed_templates(centers)
        _seed_settings(people)
        for spec in sorted(ORDERS, key=lambda s: s.order_seq):
            _seed_order(spec, centers, people, actor_id, today)
        _bump_counter(today)
