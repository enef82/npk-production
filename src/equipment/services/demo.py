"""Демо-данные модуля «Оборудование и ТО» — копия набора прототипа (`MACH_DEF`,
`seedMachines`, `seedRepairs`): 10 станков, журнал наработки за 8 недель, виды ТО
с последними проведёнными, аварии с ремонтами, один станок в ремонте.

Генератор детерминированный: «случайные» числа — хеш строки-ключа (как `hsh`
прототипа), а не `random` — повторный сид на чистой базе даёт те же значения
относительно сегодняшней даты. Идемпотентен: если оборудование уже есть, ничего не
делает.

Аварии проходят штатным путём (`create_repair` → `close_repair`): закрытие пишет
простой в наработку и публикует `equipment.repair_closed`, как в прототипе
(`seedRepairs` переносит часы в табель). История ТО — до начала журнала, поэтому
записи ТО и их ремонты создаются напрямую, без события: табель за те месяцы не
ведётся.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from src.core.numbering import facade as numbering
from src.core.org import facade as org
from src.equipment.calculations import round1
from src.equipment.models import (
    DownReason,
    Equipment,
    EquipmentStatus,
    FailureCategory,
    IdleReason,
    MaintenanceRecord,
    MaintenanceType,
    Repair,
    RepairKind,
    RepairStatus,
    RepairWorker,
    RuntimeLog,
    RuntimeSource,
)
from src.equipment.services.equipment import (
    EquipmentDTO,
    MaintenanceTypeDTO,
    create_equipment,
    create_maintenance_type,
)
from src.equipment.services.repair import (
    NUMERATOR_CODE,
    RepairDTO,
    WorkerDTO,
    close_repair,
    create_repair,
    start_repair,
)

# (инв. №, наименование, участок прототипа, система управления, [(вид ТО, интервал, работы)],
#  подключение). Участок — код прототипа: только для профиля загрузки; `work_center_id`
#  проставит модуль `production`, когда появятся участки (И2 — без FK).
MACHINES: tuple[tuple[str, str, str, str, tuple[tuple[str, int, str], ...], str], ...] = (
    ("ИН-0012", "Лазерный станок оптоволоконный 3 кВт, 3000×1500", "list", "ЧПУ CypCut",
     (("ТО-1", 250, "чистка оптики и сопла, проверка газа"),
      ("ТО-2", 1000, "замена фильтров чиллера, юстировка луча")),
     "Ethernet, выгрузка журнала заданий"),
    ("ИН-0013", "Листогибочный пресс с ЧПУ 100 т / 3200", "list", "ЧПУ Delem DA-66",
     (("ТО-1", 500, "смазка, проверка гидравлики"),
      ("ТО-2", 2000, "замена гидравлического масла")),
     "Ethernet, счётчик ходов"),
    ("ИН-0021", "Токарный станок с ЧПУ 16А20Ф3", "meh", "ЧПУ NC-201",
     (("ТО-1", 300, "смазка направляющих, замена СОЖ"),
      ("ТО-2", 1500, "проверка люфтов, ремни, подшипники шпинделя")),
     "нет порта — датчик тока на шпиндель"),
    ("ИН-0022", "Токарный обрабатывающий центр с ЧПУ", "meh", "ЧПУ Fanuc 0i-TF",
     (("ТО-1", 300, "смазка, СОЖ, проверка револьверной головки"),
      ("ТО-2", 1500, "диагностика шпинделя, замена фильтров")),
     "Ethernet, FOCAS / MTConnect"),
    ("ИН-0023", "Вертикально-фрезерный центр VMC-850", "meh", "ЧПУ Fanuc 0i-MF",
     (("ТО-1", 300, "смазка, СОЖ, чистка магазина инструмента"),
      ("ТО-2", 1500, "проверка геометрии, шпиндель")),
     "Ethernet, FOCAS / MTConnect"),
    ("ИН-0024", "Ленточнопильный станок полуавтомат", "meh", "—",
     (("ТО-1", 200, "натяжение и замена ленты, СОЖ"),),
     "датчик тока"),
    ("ИН-0031", "Сварочный полуавтомат 500 А, пост №1", "svar", "—",
     (("ТО-1", 400, "чистка подающего механизма, горелка"),),
     "—"),
    ("ИН-0032", "Сварочный полуавтомат 500 А, пост №2", "svar", "—",
     (("ТО-1", 400, "чистка подающего механизма, горелка"),),
     "—"),
    ("ИН-0041", "Камера порошковой окраски с печью полимеризации", "pok", "контроллер печи",
     (("ТО-1", 160, "замена фильтров камеры"),
      ("ТО-2", 1000, "чистка печи, проверка горелки и датчиков")),
     "Modbus, температура и время цикла"),
    ("ИН-0051", "Компрессор винтовой 11 кВт", "", "контроллер",
     (("ТО-1", 500, "замена масла и фильтров"),
      ("ТО-2", 2000, "замена сепаратора")),
     "Modbus, моточасы"),
)  # fmt: skip

# Средняя загрузка по участку прототипа (`u0`).
BASE_UTILIZATION = {
    "list": Decimal("0.72"),
    "meh": Decimal("0.66"),
    "svar": Decimal("0.55"),
    "pok": Decimal("0.5"),
    "": Decimal("0.7"),
}
# Вид ТО, состояние которого прототип задаёт явно (просрочено / скоро): (инв. №, индекс
# вида) → насколько моточасов назад было последнее ТО относительно интервала.
FORCED_MAINTENANCE_AGO = {
    ("ИН-0012", 0): Decimal("12"),  # интервал + 12 — просрочено
    ("ИН-0041", 0): Decimal("-9"),  # интервал − 9 — скоро
    ("ИН-0023", 0): Decimal("-20"),  # интервал − 20 — скоро
}
BROKEN_INVENTORY_NO = "ИН-0024"

# Сотрудники прототипа (`EMP`), которых демо ставит исполнителями ремонтов: мастер,
# операторы участков (`operatorFor`), электромонтажник.
MASTER = "Гусев И.Д."
ELECTRICIAN = "Комаров В.В."
OPERATORS = {
    "list": "Ткаченко Р.М.",
    "meh": "Захаров А.П.",
    "svar": "Яковлев Д.И.",
    "pok": "Соколова Т.Н.",
}
FAILURE_TEXTS = (
    "срабатывание защиты",
    "утечка гидравлики",
    "ошибка привода оси",
    "обрыв ленты",
    "засор форсунки",
)
FIXES = (
    "Замена узла",
    "Регулировка, наладка",
    "Замена датчика",
    "Устранение утечки, замена уплотнений",
    "Перезагрузка, восстановление параметров",
)
IDLE_WEIGHTS = (35, 25, 15, 15, 10)
CATEGORY_WEIGHTS = (30, 15, 20, 15, 10, 10)
HISTORY_DAYS = 56


def _noise(*parts: object) -> Decimal:
    """Детерминированное число в [0, 1) с 4 знаками — FNV-1a от ключа (`hsh`)."""

    value = 2166136261
    for char in "|".join(str(part) for part in parts):
        value ^= ord(char)
        value = (value * 16777619) & 0xFFFFFFFF
    return Decimal(value % 10000) / Decimal(10000)


def _uniform(low: str, high: str, *key: object) -> Decimal:
    lo, hi = Decimal(low), Decimal(high)
    return lo + (hi - lo) * _noise(*key)


def _pick[T](items: tuple[T, ...], weights: tuple[int, ...], *key: object) -> T:
    target = _noise(*key) * sum(weights)
    for item, weight in zip(items, weights, strict=True):
        target -= weight
        if target < 0:
            return item
    return items[0]


def _match_employee(short_name: str, employees: list[org.EmployeeBrief]) -> UUID | None:
    """ФИО прототипа «Гусев И.Д.» ↔ сотрудник «Гусев И.Д.» или «Гусев Иван Дмитриевич»."""

    surname, _, initials = short_name.partition(" ")
    wanted = initials.replace(".", "")
    for brief in employees:
        parts = brief.full_name.replace(".", ". ").split()
        if not parts or parts[0] != surname:
            continue
        if "".join(part[0] for part in parts[1:3]) == wanted:
            return brief.id
    return None


def _ensure_reference() -> None:
    """Справочники засевает миграция; здесь — на случай очищенной базы (`flush`)."""

    for order, name in enumerate(
        ("Нет задания", "Ожидание материала", "Ожидание УП / КД", "Нет оператора", "Наладка"),
        start=1,
    ):
        IdleReason.objects.get_or_create(name=name, defaults={"order": order})
    for order, (name, kind) in enumerate(
        (
            ("Авария", RepairKind.FAILURE),
            ("Плановое ТО", RepairKind.MAINTENANCE),
            ("Ремонт", RepairKind.REPAIR),
        ),
        start=1,
    ):
        DownReason.objects.get_or_create(name=name, defaults={"order": order, "repair_kind": kind})
    for order, name in enumerate(
        (
            "Механика",
            "Гидравлика",
            "Электрика",
            "Электроника / ЧПУ",
            "Пневматика",
            "Износ оснастки",
        ),
        start=1,
    ):
        FailureCategory.objects.get_or_create(name=name, defaults={"order": order})


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return timezone.make_aware(datetime.combine(day, time(hour, minute)))


def seed_demo() -> None:
    if Equipment.objects.exists():
        return
    with transaction.atomic():
        _ensure_reference()
        employees = org.list_active_employees()
        people = {
            name: _match_employee(name, employees)
            for name in (MASTER, ELECTRICIAN, *OPERATORS.values())
        }
        today = timezone.localdate()
        for spec in MACHINES:
            _seed_machine(spec, today, people)


def _seed_machine(
    spec: tuple[str, str, str, str, tuple[tuple[str, int, str], ...], str],
    today: date,
    people: dict[str, UUID | None],
) -> None:
    inventory_no, name, area, control, maintenance, connection = spec
    initial = Decimal(int(_uniform("2500", "9000", inventory_no, "hours")))
    equipment = create_equipment(
        EquipmentDTO(
            inventory_no=inventory_no,
            name=name,
            control_system=control,
            connection=connection,
            operating_hours_initial=initial,
        ),
        actor_id=None,
    )
    idle_reasons = tuple(IdleReason.objects.order_by("order"))
    utilization = BASE_UTILIZATION[area]
    is_cnc = "ЧПУ" in control
    failures: list[tuple[date, Decimal]] = []
    logs: list[RuntimeLog] = []
    for back in range(HISTORY_DAYS, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() >= 5:
            continue
        key = (inventory_no, day)
        load = utilization * _uniform("0.7", "1.25", *key, "u")
        run = round1(Decimal("8") * min(Decimal("0.95"), max(Decimal("0.15"), load)))
        setup = round1(_uniform("0.3", "1.2", *key, "s")) if is_cnc else Decimal("0")
        idle = round1(max(Decimal("0"), Decimal("8") - run - setup))
        if _noise(*key, "fail") < Decimal("0.05"):
            failures.append((day, round1(_uniform("2", "6", *key, "down"))))
        logs.append(
            RuntimeLog(
                equipment=equipment,
                date=day,
                run=run,
                setup=setup,
                idle=idle,
                idle_reason=(
                    _pick(idle_reasons, IDLE_WEIGHTS, *key, "reason") if idle > 0 else None
                ),
                source=RuntimeSource.MANUAL,
            )
        )
    RuntimeLog.objects.bulk_create(logs)

    master = people.get(MASTER)
    operator = people.get(OPERATORS.get(area, ""))
    for day, down in failures:
        _seed_failure(equipment, area, day, down, master, operator, people.get(ELECTRICIAN))

    current = initial + sum((log.run for log in logs), Decimal("0"))
    for index, (code, interval, scope) in enumerate(maintenance):
        mtype = create_maintenance_type(
            equipment.id,
            MaintenanceTypeDTO(code=code, interval_hours=Decimal(interval), scope=scope),
            actor_id=None,
        )
        _seed_last_maintenance(
            equipment, mtype, index, current, utilization, today, master, operator
        )

    if inventory_no == BROKEN_INVENTORY_NO:
        _seed_open_repair(equipment, today, master, operator)


def _workers(*pairs: tuple[UUID | None, Decimal]) -> list[WorkerDTO]:
    result: dict[UUID, Decimal] = {}
    for employee_id, hours in pairs:
        if employee_id is not None and hours > 0:
            result[employee_id] = result.get(employee_id, Decimal("0")) + hours
    return [WorkerDTO(employee_id=eid, hours=hours) for eid, hours in result.items()]


def _seed_failure(
    equipment: Equipment,
    area: str,
    day: date,
    down: Decimal,
    master: UUID | None,
    operator: UUID | None,
    electrician: UUID | None,
) -> None:
    key = (equipment.inventory_no, day)
    started = _at(day, 9 + int(_noise(*key, "h") * 5), int(_noise(*key, "m") * 50))
    finished = started + timedelta(minutes=int(down * 60))
    categories = tuple(FailureCategory.objects.order_by("order"))
    workers = _workers(
        (master, round1(down * _uniform("0.5", "0.9", *key, "wm"))),
        (operator, round1(down * _uniform("0.4", "0.8", *key, "wo"))),
        (
            electrician if _noise(*key, "el") < Decimal("0.3") else None,
            round1(_uniform("1", "3", *key, "we")),
        ),
    )
    data = RepairDTO(
        kind=RepairKind.FAILURE,
        started_at=started,
        finished_at=finished,
        category_id=_pick(categories, CATEGORY_WEIGHTS, *key, "cat").id,
        alarm_code=f"E-{100 + int(_noise(*key, 'alarm') * 400)}",
        description=_pick(FAILURE_TEXTS, (1, 1, 1, 1, 1), *key, "text"),
        fix=_pick(FIXES, (1, 1, 1, 1, 1), *key, "fix"),
        workers=workers,
    )
    repair = create_repair(equipment.id, data, actor_id=None)
    if workers:
        close_repair(repair.id, actor_id=None)
        return
    # Сотрудников прототипа в базе нет — закрыть штатно нельзя (исполнители
    # обязательны); запись закрывается напрямую, простой — в наработку суток.
    Repair.objects.filter(id=repair.id).update(status=RepairStatus.DONE)
    reason = DownReason.objects.get(repair_kind=RepairKind.FAILURE)
    log = RuntimeLog.objects.filter(equipment=equipment, date=day).first()
    if log is not None:
        log.down = min(Decimal("8"), log.down + down)
        log.run = max(Decimal("0"), log.run - down)
        log.down_reason = reason
        log.save(update_fields=["down", "run", "down_reason", "updated_at"])
    Equipment.objects.filter(id=equipment.id).update(status=EquipmentStatus.RUN)


def _seed_last_maintenance(
    equipment: Equipment,
    mtype: MaintenanceType,
    index: int,
    current: Decimal,
    utilization: Decimal,
    today: date,
    master: UUID | None,
    operator: UUID | None,
) -> None:
    interval = mtype.interval_hours
    forced = FORCED_MAINTENANCE_AGO.get((equipment.inventory_no, index))
    ago = (
        interval + forced
        if forced is not None
        else interval * _uniform("0.3", "0.85", equipment.inventory_no, mtype.code, "ago")
    )
    at_hours = round1(current - ago)
    per_day = max(Decimal("1"), utilization * Decimal("8"))
    days_ago = int((ago / per_day * Decimal("1.4")).quantize(Decimal("1"), ROUND_HALF_UP))
    day = today - timedelta(days=days_ago)
    MaintenanceRecord.objects.create(
        maintenance_type=mtype, date=day, at_hours=at_hours, performed_by_id=master
    )
    hours = round1(_uniform("2", "5", equipment.inventory_no, mtype.code, "h"))
    started = _at(day, 13)
    repair = Repair.objects.create(
        number=numbering.issue_number(NUMERATOR_CODE),
        equipment=equipment,
        kind=RepairKind.MAINTENANCE,
        maintenance_type=mtype,
        started_at=started,
        finished_at=started + timedelta(hours=int(hours) + 1),
        description=f"{mtype.code}: {mtype.scope}",
        fix="выполнено по регламенту",
        status=RepairStatus.DONE,
    )
    RepairWorker.objects.bulk_create(
        [
            RepairWorker(repair=repair, employee_id=w.employee_id, hours=w.hours)
            for w in _workers((master, round1(hours * Decimal("0.6"))), (operator, hours))
        ]
    )


def _seed_open_repair(
    equipment: Equipment, today: date, master: UUID | None, operator: UUID | None
) -> None:
    """Ленточная пила в ремонте: износ роликов, ждём запчасть (прототип, `m06`)."""

    wear = FailureCategory.objects.get(name="Износ оснастки")
    repair = create_repair(
        equipment.id,
        RepairDTO(
            kind=RepairKind.FAILURE,
            started_at=_at(today - timedelta(days=1), 10),
            category_id=wear.id,
            alarm_code="E-310",
            description="Износ направляющих роликов, ждём запчасть (2–3 дня)",
            parts="Ролики направляющие — заявка в закупку",
            workers=_workers((master, Decimal("3")), (operator, Decimal("2"))),
        ),
        actor_id=None,
    )
    start_repair(repair.id, actor_id=None)
