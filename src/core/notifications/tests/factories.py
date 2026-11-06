import factory

from src.core.accounts.tests.factories import UserFactory
from src.core.notifications.models import (
    Notification,
    NotificationChannel,
    NotificationDeliveryMode,
    NotificationStatus,
    NotificationTemplate,
)


class NotificationTemplateFactory(factory.django.DjangoModelFactory[NotificationTemplate]):
    class Meta:
        model = NotificationTemplate

    code = factory.Sequence(lambda n: f"tests.notification{n}")
    channel = NotificationChannel.IN_APP
    subject_template = "Тема {{ значение }}"
    body_template = "Текст {{ значение }}"


class NotificationFactory(factory.django.DjangoModelFactory[Notification]):
    class Meta:
        model = Notification

    user = factory.SubFactory(UserFactory)
    code = factory.Sequence(lambda n: f"tests.notification{n}")
    channel = NotificationChannel.IN_APP
    delivery_mode = NotificationDeliveryMode.DIGEST
    subject = factory.Sequence(lambda n: f"Тема {n}")
    body = factory.Sequence(lambda n: f"Текст {n}")
    context = factory.LazyFunction(dict)
    status = NotificationStatus.PENDING
