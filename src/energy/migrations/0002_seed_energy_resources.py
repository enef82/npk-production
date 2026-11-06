"""Состав энергоресурсов — `docs/spec/00-prilozhenie-proizvodstvo.md` §3.7 (прототип
`ERES`). Тарифы здесь не задаются: тариф — значение заказчика, его вносит энергетик
(`services.resource.set_tariff`); демо-тарифы прототипа ставит `seed_demo()`."""

from decimal import Decimal

from django.db import migrations

# (code, name, unit, order)
RESOURCES = (
    ("el", "Электроэнергия", "кВт·ч", 1),
    ("gas", "Природный газ", "м³", 2),
    ("air", "Сжатый воздух", "м³", 3),
    ("n2", "Азот", "м³", 4),
    ("heat", "Тепловая энергия", "Гкал", 5),
    ("water", "Вода", "м³", 6),
)


def seed(apps, schema_editor):
    EnergyResource = apps.get_model("energy", "EnergyResource")
    for code, name, unit, order in RESOURCES:
        EnergyResource.objects.get_or_create(
            code=code,
            defaults={"name": name, "unit": unit, "order": order, "tariff": Decimal("0")},
        )


def unseed(apps, schema_editor):
    apps.get_model("energy", "EnergyResource").objects.filter(
        code__in=[row[0] for row in RESOURCES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("energy", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
