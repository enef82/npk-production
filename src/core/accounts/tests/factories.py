import factory

from src.core.accounts.models import User


class UserFactory(factory.django.DjangoModelFactory[User]):
    class Meta:
        model = User
        django_get_or_create = ("email",)
        skip_postgeneration_save = False

    email = factory.Sequence(lambda n: f"user{n}@npk-prod.local")
    display_name = factory.Sequence(lambda n: f"Пользователь {n}")
    is_active = True
    password = factory.PostGenerationMethodCall("set_password", "password123!")
