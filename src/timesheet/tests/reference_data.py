"""Ожидаемый состав справочника кодов вида времени — спецификация §3.5 и прототип (TC).

Отдельная копия, а не импорт из миграции (`docs/checklist-novyy-modul.md` §9): тест
состава сверяет миграцию с этим списком, а фикстура `conftest._time_codes`
восстанавливает его после `flush()` транзакционных тестов на `--reuse-db`.
"""

from decimal import Decimal

# код, наименование, рабочее, разносится, коэффициент
TIME_CODES: tuple[tuple[str, str, bool, bool, Decimal], ...] = (
    ("Я", "Явка", True, True, Decimal("1")),
    ("РВ", "Работа в выходной", True, True, Decimal("2")),
    ("С", "Сверхурочные", True, True, Decimal("1.5")),
    ("К", "Командировка", True, True, Decimal("1")),
    ("ВП", "Простой по вине работодателя", False, False, Decimal("1")),
    ("ОТ", "Отпуск", False, False, Decimal("1")),
    ("Б", "Больничный", False, False, Decimal("1")),
    ("ДО", "Без сохранения", False, False, Decimal("1")),
    ("ПР", "Прогул", False, False, Decimal("1")),
    ("НН", "Неявка невыясненная", False, False, Decimal("1")),
)
