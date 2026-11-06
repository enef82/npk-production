import pytest
import redis
from django.db.backends.base.base import BaseDatabaseWrapper
from django.db.utils import OperationalError
from django.test import Client


@pytest.mark.django_db
def test_health_endpoint_возвращает_ok(client: Client) -> None:
    response = client.get("/health/")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"] is True
    assert body["redis"] is True


def test_health_показывает_недоступность_бд(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(self: BaseDatabaseWrapper) -> None:
        raise OperationalError("нет соединения с БД")

    monkeypatch.setattr(BaseDatabaseWrapper, "ensure_connection", _raise)
    response = client.get("/health/")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["db"] is False


def test_health_показывает_недоступность_redis(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(self: redis.Redis) -> None:
        raise redis.ConnectionError("нет соединения с Redis")

    monkeypatch.setattr(redis.Redis, "ping", _raise)
    response = client.get("/health/")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "error"
    assert body["redis"] is False


def test_healthz_отвечает_даже_если_бд_недоступна(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(self: BaseDatabaseWrapper) -> None:
        raise OperationalError("нет соединения с БД")

    monkeypatch.setattr(BaseDatabaseWrapper, "ensure_connection", _raise)
    response = client.get("/healthz")

    assert response.status_code == 200
