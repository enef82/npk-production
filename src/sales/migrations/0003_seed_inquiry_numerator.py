"""Нумератор заявки `sales.inquiry` (`З-{seq:04d}`, без сброса по году) заводится
миграцией с данными — без строки создание заявки не работает «из коробки». Тот же набор —
в `tests/reference_data.py`: transactional-тесты стирают посев миграций."""

from django.db import migrations

NUMERATOR_CODE = "sales.inquiry"


def seed_inquiry_numerator(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    Numerator.objects.get_or_create(
        code=NUMERATOR_CODE,
        defaults={
            "name": "Заявка на просчёт",
            "template": "З-{seq:04d}",
            "legal_entity": None,
            "reset_period": "never",
            "is_active": True,
        },
    )


def unseed_inquiry_numerator(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    Numerator.objects.filter(code=NUMERATOR_CODE).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("sales", "0002_calc_dependency_same_inquiry"),
        ("core_numbering", "0001_numerator_template_and_legal_entity"),
    ]

    operations = [
        migrations.RunPython(seed_inquiry_numerator, unseed_inquiry_numerator),
    ]
