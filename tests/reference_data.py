"""Справочные данные, которые засеивают миграции и которые восстанавливает
`ensure_core_reference_data` (корневой `conftest.py`) после `flush()` transactional-тестов
на `--reuse-db`. Сознательно не импортируется из миграций: миграция фиксирует состояние
на момент применения, а этот список — то, что тесты обязаны видеть сейчас."""

from src.core.numbering.models import NumeratorResetPeriod
from src.core.org.models import PositionCategory

# (code, name, template, reset_period) — нумераторы модулей приложения.
CORE_NUMERATORS: tuple[tuple[str, str, str, str], ...] = (
    (
        "equipment.repair",
        "Авария / ремонт оборудования",
        "АР-{seq:04d}",
        NumeratorResetPeriod.NEVER,
    ),
    (
        "production.order",
        "Производственный заказ",
        "ПЗ-{year}-{seq:04d}",
        NumeratorResetPeriod.YEARLY,
    ),
    ("sales.inquiry", "Заявка на просчёт", "З-{seq:04d}", NumeratorResetPeriod.NEVER),
)

# (code, name) — виды документов заказа, см. `production.migrations.0005_seed_document_types`.
CORE_DOCUMENT_TYPES: tuple[tuple[str, str], ...] = (
    ("production.kd", "КД"),
    ("production.drawing", "Чертёж"),
    ("production.tz", "ТЗ / опросный лист"),
    ("production.specification", "Спецификация"),
    ("production.process", "Техпроцесс"),
    ("production.cnc", "УП ЧПУ"),
    ("production.other", "Прочее"),
)
DOCUMENT_MAX_SIZE_BYTES = 100 * 1024 * 1024

# (name, category) — см. `core.org.migrations.0003_seed_trade_positions`.
CORE_TRADE_POSITIONS = (
    ("Электромонтажник", PositionCategory.WORKER),
    ("Монтажник КИПиА", PositionCategory.WORKER),
    ("Монтажник", PositionCategory.WORKER),
    ("Сварщик", PositionCategory.WORKER),
    ("Мастер", PositionCategory.MANAGER),
)
