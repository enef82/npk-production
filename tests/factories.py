import factory

from src.core.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory[User]):
    class Meta:
        model = User
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"user{n}@npk-prod.local")
    display_name = "Тест Тестов"
