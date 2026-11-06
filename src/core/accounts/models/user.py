"""Пользователь. AUTH_USER_MODEL. Аутентификация по email, без username — служебные
учётные записи (шлюз 1С и т.п.) не имеют Employee и отображаются по display_name."""

from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.db import models

from src.core.audit.tracking import track
from src.core.common.models import TimeStampedModel, UUIDPrimaryKeyModel

from .manager import UserManager


@track(exclude=["password"])  # хеш пароля незачем копить в истории — не даёт пользы аудиту
class User(UUIDPrimaryKeyModel, TimeStampedModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("Email", unique=True)
    display_name = models.CharField("Отображаемое имя", max_length=255)
    is_active = models.BooleanField("Активен", default=True)
    is_staff = models.BooleanField("Доступ в админку", default=False)

    objects = UserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["display_name"]

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"
        ordering = ["email"]

    def __str__(self) -> str:
        return self.display_name or self.email
