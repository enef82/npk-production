import factory

from src.core.events.models import OutboxEvent


class OutboxEventFactory(factory.django.DjangoModelFactory[OutboxEvent]):
    class Meta:
        model = OutboxEvent

    event_type = "core_events.example.widget_touched"
    version = 1
    aggregate_id = factory.Faker("uuid4")
    payload = factory.LazyFunction(dict)
