"""Нумератор журнала ремонтов заводится миграцией с данными — без строки
`code="equipment.repair"` регистрация аварии не работает «из коробки» (прецедент
`production.migrations.0003_seed_order_numerator` ИС). Та же строка — в
`tests/reference_data.py` (`CORE_NUMERATORS`)."""

from django.db import migrations

NUMERATOR_CODE = "equipment.repair"


def seed_repair_numerator(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    Numerator.objects.get_or_create(
        code=NUMERATOR_CODE,
        defaults={
            "name": "Авария / ремонт оборудования",
            "template": "АР-{seq:04d}",
            "legal_entity": None,
            "reset_period": "never",
            "is_active": True,
        },
    )


def unseed_repair_numerator(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    Numerator.objects.filter(code=NUMERATOR_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0001_initial"),
        ("core_numbering", "0001_numerator_template_and_legal_entity"),
    ]

    operations = [
        migrations.RunPython(seed_repair_numerator, unseed_repair_numerator),
    ]
