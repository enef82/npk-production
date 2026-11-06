"""Нумераторы заявки на закупку и заказа поставщику — без строк `supply.requisition` и
`supply.purchase_order` передать позиции в закупку и оформить заказ нельзя «из коробки».
Тот же набор — в `tests/reference_data.py`: transactional-тесты стирают посев миграций."""

from django.db import migrations

NUMERATORS = (
    ("supply.requisition", "Заявка на закупку", "ЗЗ-{year}-{seq:04d}"),
    ("supply.purchase_order", "Заказ поставщику", "ЗП-{year}-{seq:04d}"),
)


def seed(apps, schema_editor):
    Numerator = apps.get_model("core_numbering", "Numerator")
    for code, name, template in NUMERATORS:
        Numerator.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "template": template,
                "legal_entity": None,
                "reset_period": "yearly",
                "is_active": True,
            },
        )


def unseed(apps, schema_editor):
    apps.get_model("core_numbering", "Numerator").objects.filter(
        code__in=[code for code, _, _ in NUMERATORS]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("supply", "0001_initial"),
        ("core_numbering", "0001_numerator_template_and_legal_entity"),
    ]

    operations = [migrations.RunPython(seed, unseed)]
