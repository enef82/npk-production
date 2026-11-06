"""Контрагент — ядро идентичности. Ровно семь полей, не расширять."""

from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q, UniqueConstraint

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .choices import PartyStatus, PartyType


@track()
class Party(UUIDPrimaryKeyModel, TimeStampedModel):
    inn = models.CharField("ИНН", max_length=12, blank=True)
    kpp = models.CharField("КПП", max_length=9, blank=True)
    legal_name = models.CharField("Полное наименование", max_length=512)
    short_name = models.CharField("Краткое наименование", max_length=255)
    party_type = models.CharField("Тип контрагента", max_length=16, choices=PartyType.choices)
    status = models.CharField(
        "Статус", max_length=16, choices=PartyStatus.choices, default=PartyStatus.DRAFT
    )

    class Meta:
        verbose_name = "Контрагент"
        verbose_name_plural = "Контрагенты"
        permissions = [
            (
                "force_create_party",
                "Может создать контрагента вопреки найденным дубликатам",
            ),
        ]
        constraints = [
            UniqueConstraint(
                fields=["inn", "kpp"],
                condition=~Q(status=PartyStatus.ARCHIVED) & ~Q(inn=""),
                name="core_identity_party_uniq_active_inn_kpp",
            ),
            models.CheckConstraint(
                condition=Q(party_type=PartyType.LEGAL) | Q(kpp=""),
                name="core_identity_party_kpp_only_for_legal",
            ),
        ]
        indexes = [
            GinIndex(
                fields=["short_name"],
                opclasses=["gin_trgm_ops"],
                name="core_identity_party_name_trgm",
            ),
        ]

    def __str__(self) -> str:
        return self.short_name
