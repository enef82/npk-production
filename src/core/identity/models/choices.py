"""Статусные и типовые перечисления ядра идентичности."""

from django.db import models


class PartyType(models.TextChoices):
    LEGAL = "legal", "Юридическое лицо"
    ENTREPRE = "entrepre", "Индивидуальный предприниматель"
    PERSON = "person", "Физическое лицо"
    FOREIGN = "foreign", "Нерезидент"


class PartyStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    ACTIVE = "active", "Активен"
    BLOCKED = "blocked", "Заблокирован"
    ARCHIVED = "archived", "Архив"


class ItemType(models.TextChoices):
    PRODUCT = "product", "Изделие"
    MATERIAL = "material", "Материал"
    SERVICE = "service", "Услуга"


class ItemStatus(models.TextChoices):
    DRAFT = "draft", "Черновик"
    ACTIVE = "active", "Активен"
    ARCHIVED = "archived", "Архив"
