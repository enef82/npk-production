"""Коды видов времени прототипа (TC): состав, признаки и коэффициенты стоимости
(`docs/spec/00-prilozhenie-proizvodstvo.md` §3.5). Тестовая копия списка —
`src/timesheet/tests/reference_data.py`."""

from decimal import Decimal

from django.db import migrations

TIME_CODES = [
    # код, наименование, рабочее, разносится, коэффициент
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
]


def seed(apps, schema_editor):
    TimeCode = apps.get_model("timesheet", "TimeCode")
    for order, (code, name, is_work, is_allocatable, multiplier) in enumerate(TIME_CODES):
        TimeCode.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "is_work": is_work,
                "is_allocatable": is_allocatable,
                "cost_multiplier": multiplier,
                "sort_order": (order + 1) * 10,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("timesheet", "0001_initial")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
