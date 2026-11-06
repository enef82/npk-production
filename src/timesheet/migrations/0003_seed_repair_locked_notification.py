"""Шаблон уведомления «часы ремонта не легли в закрытый табель» — без шаблона
`core.notifications.notify` ничего не создаёт, и начальник производства не узнал бы,
что часы ремонта нужно разнести после переоткрытия периода."""

from django.db import migrations

CODE = "timesheet.repair_hours_locked"


def seed(apps, schema_editor):
    NotificationTemplate = apps.get_model("core_notifications", "NotificationTemplate")
    NotificationTemplate.objects.get_or_create(
        code=CODE,
        channel="in_app",
        defaults={
            "subject_template": "",
            "body_template": (
                "Ремонт {{ number }} от {{ date }}: часы не разнесены в табель — период "
                "закрыт для правки. Сотрудники: {{ employees }}. Разнесите часы после "
                "переоткрытия табеля."
            ),
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("timesheet", "0002_seed_time_codes"),
        ("core_notifications", "0002_pghistory_tracking"),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
