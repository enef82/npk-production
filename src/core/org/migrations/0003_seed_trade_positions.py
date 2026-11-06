"""Должности рабочих специальностей и линейного мастера — на них ссылается состав
звена нормы (`core.costing.WorkNormLabor`, спец. CRM ИС §2.4.1).

Заводятся здесь, а не миграцией `core.costing`: штатное расписание принадлежит
организации, справочник затрат на него только ссылается (инвариант И2 — FK на `core`).
Ставки этих должностей и коэффициенты разрядов — шаг 11а, не здесь.

«Мастер» — линейный руководитель (категория «Руководитель»), ставки у него пока нет
и в нормы он не входит; место в расчёте открыто (спец. CRM ИС §10.2).
"""

from django.db import migrations

# (name, category) — категории из `core.org.models.choices.PositionCategory`.
POSITIONS = [
    ("Электромонтажник", "worker"),
    ("Монтажник КИПиА", "worker"),
    ("Монтажник", "worker"),
    ("Сварщик", "worker"),
    ("Мастер", "manager"),
]


def seed_positions(apps, schema_editor):
    Position = apps.get_model("core_org", "Position")
    for name, category in POSITIONS:
        Position.objects.get_or_create(name=name, category=category, defaults={"grade": ""})


def unseed_positions(apps, schema_editor):
    Position = apps.get_model("core_org", "Position")
    Position.objects.filter(name__in=[name for name, _ in POSITIONS]).delete()


class Migration(migrations.Migration):
    dependencies = [("core_org", "0002_pghistory_tracking")]

    operations = [
        migrations.RunPython(seed_positions, unseed_positions),
    ]
