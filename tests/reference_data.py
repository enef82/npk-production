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
)

# (name, category) — см. `core.org.migrations.0003_seed_trade_positions`.
CORE_TRADE_POSITIONS = (
    ("Электромонтажник", PositionCategory.WORKER),
    ("Монтажник КИПиА", PositionCategory.WORKER),
    ("Монтажник", PositionCategory.WORKER),
    ("Сварщик", PositionCategory.WORKER),
    ("Мастер", PositionCategory.MANAGER),
)
