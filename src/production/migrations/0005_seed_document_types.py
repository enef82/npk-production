"""Виды документов заказа (`docs/spec/00-prilozhenie-proizvodstvo.md` §3.1, «Документы»):
КД, Чертёж, ТЗ / опросный лист, Спецификация, Техпроцесс, УП ЧПУ, Прочее — `DocumentType`
ядра. Миграцией, как велит спецификация: без них загрузка документа заказа не работает.
`allowed_mime_types` пустой — «любой, кроме исполняемых» (`core.documents.services.upload`):
УП ЧПУ приходят с расширениями `.nc`, `.tap`, `.mpf`, которые заранее не перечислить.
Тот же набор — в `tests/reference_data.py`."""

from django.db import migrations

MAX_SIZE_BYTES = 100 * 1024 * 1024

DOCUMENT_TYPES = (
    ("production.kd", "КД"),
    ("production.drawing", "Чертёж"),
    ("production.tz", "ТЗ / опросный лист"),
    ("production.specification", "Спецификация"),
    ("production.process", "Техпроцесс"),
    ("production.cnc", "УП ЧПУ"),
    ("production.other", "Прочее"),
)


def seed_document_types(apps, schema_editor):
    DocumentType = apps.get_model("core_documents", "DocumentType")
    for code, name in DOCUMENT_TYPES:
        DocumentType.objects.get_or_create(
            code=code,
            defaults={
                "name": name,
                "allowed_mime_types": [],
                "max_size_bytes": MAX_SIZE_BYTES,
                "is_active": True,
            },
        )


def unseed_document_types(apps, schema_editor):
    DocumentType = apps.get_model("core_documents", "DocumentType")
    DocumentType.objects.filter(code__in=[code for code, _ in DOCUMENT_TYPES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("production", "0004_seed_order_numerator"),
        ("core_documents", "0004_document_change_note"),
    ]

    operations = [
        migrations.RunPython(seed_document_types, unseed_document_types),
    ]
