import factory

from src.core.numbering.models import Numerator, NumeratorResetPeriod


class NumeratorFactory(factory.django.DjangoModelFactory[Numerator]):
    class Meta:
        model = Numerator

    code = factory.Sequence(lambda n: f"test.numerator{n}")
    name = factory.Sequence(lambda n: f"Нумератор {n}")
    template = "{seq:05d}"
    legal_entity = None
    reset_period = NumeratorResetPeriod.YEARLY
    is_active = True
