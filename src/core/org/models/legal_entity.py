"""Профиль ядра для НАШИХ юрлиц. Реквизиты и адреса не дублируются — они привязаны
к Party отдельными таблицами (docs/spec §3.6–3.7)."""

from django.db import models

from src.core.audit.tracking import track
from src.core.identity.profiles import PartyProfile

from .choices import TaxSystem


@track()
class LegalEntity(PartyProfile):
    print_name = models.CharField("Краткое наименование для печатных форм", max_length=255)
    is_primary = models.BooleanField("Основная организация", default=False)
    tax_system = models.CharField(
        "Система налогообложения", max_length=32, choices=TaxSystem.choices
    )
    default_signatory = models.ForeignKey(
        "core_org.Employee",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="signatory_for_legal_entities",
        verbose_name="Подписант по умолчанию",
    )

    class Meta:
        verbose_name = "Юридическое лицо"
        verbose_name_plural = "Юридические лица"
        constraints = [
            models.UniqueConstraint(
                fields=["is_primary"],
                condition=models.Q(is_primary=True),
                name="core_org_legalentity_uniq_primary",
            ),
        ]

    def __str__(self) -> str:
        return self.print_name
