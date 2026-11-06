"""Справочник причин брака — состав прототипа «Производство» (`CAUSES`). Без него нельзя
записать брак (ограничение `quality_record_defect_classified`). «Оператор» помечена
признаком `is_operator_fault` — по нему считается брак по вине оператора (§3.3).

Точки контроля и виды дефектов здесь не засеиваются: точка ссылается на участок
`production`, а участки заводит `production.seed_demo`, а не миграция, — их засевает
`quality.seed_demo`."""

from django.db import migrations

# (наименование, по вине оператора)
CAUSES = (
    ("Оператор", True),
    ("Оборудование", False),
    ("Материал / комплектующие", False),
    ("КД / УП ЧПУ", False),
    ("Технология", False),
    ("Прочее", False),
)


def seed(apps, schema_editor):
    DefectCause = apps.get_model("quality", "DefectCause")
    for order, (name, is_operator) in enumerate(CAUSES, start=1):
        DefectCause.objects.get_or_create(
            name=name, defaults={"order": order, "is_operator_fault": is_operator}
        )


def unseed(apps, schema_editor):
    apps.get_model("quality", "DefectCause").objects.filter(
        name__in=[name for name, _ in CAUSES]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("quality", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
