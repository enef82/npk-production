from django.db import models
from uuid6 import uuid7


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата изменения", auto_now=True)

    class Meta:
        abstract = True


class UUIDPrimaryKeyModel(models.Model):
    id = models.UUIDField(
        "Идентификатор",
        primary_key=True,
        default=uuid7,
        editable=False,
    )

    class Meta:
        abstract = True
