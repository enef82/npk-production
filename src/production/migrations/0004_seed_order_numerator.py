"""Нумератор производственного заказа заводится миграцией с данными — без строки
`code="production.order"` запуск заявки не работает «из коробки» (прецедент ИС
`production.migrations.0003_seed_order_numerator`). Тот же набор — в
`tests/reference_data.py`: transactional-тесты стирают посев миграций."""

from django.db import migrations

NUMERATOR_CODE = "production.order"


def seed_order_numerator(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    Numerator.objects.get_or_create(
        code=NUMERATOR_CODE,
        defaults={
            "name": "Производственный заказ",
            "template": "ПЗ-{year}-{seq:04d}",
            "legal_entity": None,
            "reset_period": "yearly",
            "is_active": True,
        },
    )


def unseed_order_numerator(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    Numerator.objects.filter(code=NUMERATOR_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0003_operation_dependency_same_order"),
        ("core_numbering", "0001_numerator_template_and_legal_entity"),
    ]

    operations = [
        migrations.RunPython(seed_order_numerator, unseed_order_numerator),
    ]
