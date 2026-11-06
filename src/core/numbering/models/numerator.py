"""Нумератор — шаблон номера и настройка периодичности сброса.

Атомарная выдача номера — `core.numbering.services.issue.issue_number()`, не здесь:
модели ядра тонкие, вся логика — в services (CLAUDE.md §5, И3).

`legal_entity` — нумераторы разных юрлиц независимы (docs/spec/03-platforma.md §4):
без этого поля два юрлица делили бы один счётчик для одинаково названного нумератора.
`null=True` — часть нумераторов (например, внутренние документы) не привязана ни к
какому юрлицу.

`clean()` — вторичная защита для админки и `ModelForm` (Django вызывает `clean()`
только через них, не через обычный `save()`). Основной путь валидации шаблона —
сервис `core.numbering.services.numerator.create_numerator`, единственная точка, где
`Numerator` реально создаётся (инвариант И3), — см. тот же паттерн в
`core.identity.profiles.PartyProfile.clean()`. Оба пути зовут одну и ту же
`core.numbering.template.validate_numerator_template` — модуль без зависимостей от
`models`/`services`, поэтому обычный импорт на верхнем уровне файла, без цикла.
"""

from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel
from src.core.numbering.template import validate_numerator_template

from .choices import NumeratorResetPeriod


@track()
class Numerator(UUIDPrimaryKeyModel, TimeStampedModel):
    code = models.CharField(
        "Код",
        max_length=100,
        unique=True,
        help_text="Ключ, которым модули запрашивают номер, напр. contracts.contract",
    )
    name = models.CharField("Наименование", max_length=255)
    template = models.CharField(
        "Шаблон номера",
        max_length=128,
        help_text=(
            'Формат-строка с подстановками {year}, {month}, {seq}, напр. "ДГ-{year}-{seq:05d}"'
        ),
    )
    legal_entity = models.ForeignKey(
        "core_org.LegalEntity",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="numerators",
        verbose_name="Юридическое лицо",
    )
    reset_period = models.CharField(
        "Периодичность сброса",
        max_length=16,
        choices=NumeratorResetPeriod.choices,
        default=NumeratorResetPeriod.YEARLY,
    )
    is_active = models.BooleanField("Активен", default=True)

    class Meta:
        verbose_name = "Нумератор"
        verbose_name_plural = "Нумераторы"
        ordering = ["code"]

    def __str__(self) -> str:
        return self.name

    def clean(self) -> None:
        validate_numerator_template(self.template)
