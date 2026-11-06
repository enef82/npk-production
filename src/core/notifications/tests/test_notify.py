"""notify(): рендер шаблона по коду/каналу и уважение настроек пользователя."""

import pytest

from src.core.accounts.tests.factories import UserFactory
from src.core.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryMode,
    NotificationStatus,
    UserNotificationSetting,
)
from src.core.notifications.services import notify
from src.core.notifications.tests.factories import NotificationTemplateFactory


@pytest.mark.django_db
def test_notify_создаёт_уведомление_по_шаблону() -> None:
    пользователь = UserFactory()
    пользователь_id = пользователь.id  # type: ignore[attr-defined]
    NotificationTemplateFactory(
        code="tests.event",
        channel=NotificationChannel.IN_APP,
        subject_template="Тема: {{ значение }}",
        body_template="Текст: {{ значение }}",
    )

    созданные = notify([пользователь_id], "tests.event", {"значение": "42"})

    assert len(созданные) == 1
    уведомление = Notification.objects.get(user_id=пользователь_id, code="tests.event")
    assert уведомление.subject == "Тема: 42"
    assert уведомление.body == "Текст: 42"
    assert уведомление.status == NotificationStatus.SENT


@pytest.mark.django_db
def test_notify_не_создаёт_уведомление_при_выключенном_канале() -> None:
    пользователь = UserFactory()
    пользователь_id = пользователь.id  # type: ignore[attr-defined]
    NotificationTemplateFactory(code="tests.event", channel=NotificationChannel.IN_APP)
    UserNotificationSetting.objects.create(
        user_id=пользователь_id,
        code="tests.event",
        channel=NotificationChannel.IN_APP,
        is_enabled=False,
    )

    созданные = notify([пользователь_id], "tests.event", {})

    assert созданные == []


@pytest.mark.django_db
def test_notify_ставит_дайджестовые_в_ожидание_без_немедленной_отправки() -> None:
    пользователь = UserFactory()
    пользователь_id = пользователь.id  # type: ignore[attr-defined]
    NotificationTemplateFactory(code="tests.event", channel=NotificationChannel.IN_APP)
    UserNotificationSetting.objects.create(
        user_id=пользователь_id,
        code="tests.event",
        channel=NotificationChannel.IN_APP,
        delivery_mode=NotificationDeliveryMode.DIGEST,
    )

    notify([пользователь_id], "tests.event", {})

    уведомление = Notification.objects.get(user_id=пользователь_id, code="tests.event")
    assert уведомление.delivery_mode == NotificationDeliveryMode.DIGEST
    assert уведомление.status == NotificationStatus.PENDING
