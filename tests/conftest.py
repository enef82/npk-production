import pytest

from src.core.accounts.models import User
from tests.factories import UserFactory


@pytest.fixture
def user(db: None) -> User:
    return UserFactory()  # type: ignore[return-value]
