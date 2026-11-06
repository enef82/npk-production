"""Справочники причин простоя, причин остановки и категорий отказов — состав
прототипа «Производство» (`IDLE_R`, `DOWN_R`, `FAIL_CAT`). Без них нельзя внести
смену с простоем и закрыть аварию (ограничения `equipment_runtime_*_reason`,
`equipment_repair_failure_category`)."""

from django.db import migrations

IDLE_REASONS = ("Нет задания", "Ожидание материала", "Ожидание УП / КД", "Нет оператора", "Наладка")
# (название, вид записи ремонта, в которую ложится простой при закрытии)
DOWN_REASONS = (("Авария", "fail"), ("Плановое ТО", "maintenance"), ("Ремонт", "repair"))
FAILURE_CATEGORIES = (
    "Механика",
    "Гидравлика",
    "Электрика",
    "Электроника / ЧПУ",
    "Пневматика",
    "Износ оснастки",
)


def seed(apps, schema_editor):
    IdleReason = apps.get_model("equipment", "IdleReason")
    DownReason = apps.get_model("equipment", "DownReason")
    FailureCategory = apps.get_model("equipment", "FailureCategory")
    for order, name in enumerate(IDLE_REASONS, start=1):
        IdleReason.objects.get_or_create(name=name, defaults={"order": order})
    for order, (name, kind) in enumerate(DOWN_REASONS, start=1):
        DownReason.objects.get_or_create(name=name, defaults={"order": order, "repair_kind": kind})
    for order, name in enumerate(FAILURE_CATEGORIES, start=1):
        FailureCategory.objects.get_or_create(name=name, defaults={"order": order})


def unseed(apps, schema_editor):
    apps.get_model("equipment", "IdleReason").objects.filter(name__in=IDLE_REASONS).delete()
    apps.get_model("equipment", "DownReason").objects.filter(
        name__in=[name for name, _ in DOWN_REASONS]
    ).delete()
    apps.get_model("equipment", "FailureCategory").objects.filter(
        name__in=FAILURE_CATEGORIES
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("equipment", "0002_seed_repair_numerator")]

    operations = [migrations.RunPython(seed, unseed)]
