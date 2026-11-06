from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel


@track()
class DocumentType(TimeStampedModel, UUIDPrimaryKeyModel):
    code = models.CharField("Код", max_length=64, unique=True)
    name = models.CharField("Наименование", max_length=255)
    allowed_mime_types = models.JSONField("Допустимые MIME-типы", default=list)
    max_size_bytes = models.PositiveBigIntegerField("Максимальный размер, байт")
    # Флаг для будущей интеграции с core.approvals — сам маршрут согласования здесь не строится.
    requires_approval = models.BooleanField("Требует согласования", default=False)
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Тип документа"
        verbose_name_plural = "Типы документов"

    def __str__(self) -> str:
        return self.name
