"""Дайджест: несколько уведомлений одного пользователя/канала группируются в одно."""

import pytest

from src.core.accounts.tests.factories import UserFactory
from src.core.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryMode,
    NotificationStatus,
)
from src.core.notifications.services import build_digest_for_user_channel
from src.core.notifications.tests.factories import NotificationFactory


@pytest.mark.django_db
def test_уведомления_группируются_в_дайджест() -> None:
    пользователь = UserFactory()
    пользователь_id = пользователь.id  # type: ignore[attr-defined]
    NotificationFactory.create_batch(
        3,
        user_id=пользователь_id,
        channel=NotificationChannel.IN_APP,
        delivery_mode=NotificationDeliveryMode.DIGEST,
        status=NotificationStatus.PENDING,
    )

    дайджест = build_digest_for_user_channel(пользователь_id, NotificationChannel.IN_APP)

    assert дайджест.items.count() == 3
    assert not Notification.objects.filter(
        user_id=пользователь_id, status=NotificationStatus.PENDING
    ).exists()
    assert (
        Notification.objects.filter(
            user_id=пользователь_id, status=NotificationStatus.DIGESTED
        ).count()
        == 3
    )


@pytest.mark.django_db
def test_дайджест_не_трогает_немедленные_уведомления() -> None:
    пользователь = UserFactory()
    пользователь_id = пользователь.id  # type: ignore[attr-defined]
    NotificationFactory(
        user_id=пользователь_id,
        channel=NotificationChannel.IN_APP,
        delivery_mode=NotificationDeliveryMode.IMMEDIATE,
        status=NotificationStatus.PENDING,
    )
    NotificationFactory(
        user_id=пользователь_id,
        channel=NotificationChannel.IN_APP,
        delivery_mode=NotificationDeliveryMode.DIGEST,
        status=NotificationStatus.PENDING,
    )

    дайджест = build_digest_for_user_channel(пользователь_id, NotificationChannel.IN_APP)

    assert дайджест.items.count() == 1
    assert (
        Notification.objects.filter(
            delivery_mode=NotificationDeliveryMode.IMMEDIATE, status=NotificationStatus.PENDING
        ).count()
        == 1
    )
