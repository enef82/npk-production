"""API «Энергоучёта»: права (энергетик, технический пользователь SCADA — и разрешение,
и запрет), идемпотентный приём, отчёты без N+1."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth.models import Group, Permission
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from src.core.accounts.groups import POWER_ENGINEER, PRODUCTION_HEAD
from src.core.accounts.models import User
from src.core.accounts.signals import sync_group_permissions
from src.core.accounts.tests.factories import UserFactory
from src.energy.models import MeterInterval, MeterKind
from src.energy.tests.factories import EnergyResourceFactory, MeterFactory, MeterIntervalFactory, at

pytestmark = pytest.mark.django_db

BASE = "/api/v1/energy"
YESTERDAY = timezone.localdate() - timedelta(days=1)


def _user(*groups: str) -> User:
    sync_group_permissions()
    user: User = UserFactory.create()
    for name in groups:
        user.groups.add(Group.objects.get(name=name))
    return user


def _client(user: User) -> Client:
    client = Client()
    client.force_login(user)
    return client


def _scada_user() -> User:
    """Технический пользователь: право выдано лично, без роли."""

    user = _user()
    user.user_permissions.add(Permission.objects.get(codename="ingest_intervals"))
    # Перечитать: кэш прав `has_perm` у объекта уже заполнен без нового права.
    fresh: User = User.objects.get(id=user.id)
    return fresh


def _post(client: Client, url: str, data: dict[str, Any]) -> Any:
    return client.post(url, data, content_type="application/json")


def _envelope(message_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "source_id": "scada-ceh-1",
        "message_id": message_id,
        "items": [
            {
                "type": "energy_interval",
                "meter_code": "СЧ-ЭЭ-ВВОД",
                "start": at(YESTERDAY, 8, 30).isoformat(),
                "value": "41.25",
            }
        ],
    }


def test_технический_пользователь_scada_передаёт_пакет_идемпотентно() -> None:
    MeterFactory.create(code="СЧ-ЭЭ-ВВОД")
    client = _client(_scada_user())

    first = _post(client, f"{BASE}/intervals", _envelope("pkt-1"))
    second = _post(client, f"{BASE}/intervals", _envelope("pkt-1"))

    assert first.status_code == 200, first.content
    assert first.json() == {
        "message_id": "pkt-1",
        "duplicate": False,
        "accepted": 1,
        "rejected": 0,
        "errors": [],
    }
    assert second.json()["duplicate"] is True
    assert MeterInterval.objects.count() == 1


def test_пользователь_без_права_приёма_получает_403() -> None:
    MeterFactory.create(code="СЧ-ЭЭ-ВВОД")
    for user in (_user(), _user(POWER_ENGINEER), _user(PRODUCTION_HEAD)):
        response = _post(_client(user), f"{BASE}/intervals", _envelope(f"pkt-{user.id}"))
        assert response.status_code == 403
    assert not MeterInterval.objects.exists()


def test_неподдерживаемая_версия_формата_это_400() -> None:
    client = _client(_scada_user())
    body = {**_envelope("pkt-v2"), "schema_version": "2.0"}
    response = _post(client, f"{BASE}/intervals", body)
    assert response.status_code == 400
    assert response.json()["code"] == "unsupported_schema_version"


def test_энергетик_ведёт_счётчики_тарифы_и_показания() -> None:
    el = EnergyResourceFactory.create()
    client = _client(_user(POWER_ENGINEER))

    meter = _post(
        client,
        f"{BASE}/meters",
        {"code": "СЧ-ВОДА", "name": "Вода", "resource_id": str(el.id), "kind": "input",
         "source": "manual"},
    )  # fmt: skip
    tariff = _post(
        client,
        f"{BASE}/resources/{el.id}/tariffs",
        {"valid_from": YESTERDAY.isoformat(), "tariff": "7.9"},
    )
    reading = _post(
        client,
        f"{BASE}/meters/{meter.json()['id']}/readings",
        {"taken_at": at(YESTERDAY, 0).isoformat(), "value": "100"},
    )

    assert meter.status_code == 200, meter.content
    assert tariff.status_code == 200
    assert tariff.json()["abilities"] == {"can_manage_meters": True, "can_ingest_intervals": False}
    assert reading.status_code == 200


def test_без_роли_энергетика_счётчик_не_завести_но_отчёты_видны() -> None:
    el = EnergyResourceFactory.create()
    client = _client(_user(PRODUCTION_HEAD))

    response = _post(
        client,
        f"{BASE}/meters",
        {"code": "X", "name": "X", "resource_id": str(el.id), "kind": "input"},
    )

    assert response.status_code == 403
    assert client.get(f"{BASE}/reports/tree?resource=el").status_code == 200
    assert client.get(f"{BASE}/reports/consumption").status_code == 200
    assert client.get(f"{BASE}/reports/specific").status_code == 200


def test_период_с_началом_позже_окончания_это_400() -> None:
    client = _client(_user())
    response = client.get(f"{BASE}/reports/consumption?date_from=2026-11-05&date_to=2026-11-01")
    assert response.status_code == 400


def test_профиль_и_баланс_через_api() -> None:
    el = EnergyResourceFactory.create()
    root = MeterFactory.create(resource=el)
    child = MeterFactory.create(resource=el, parent=root, kind=MeterKind.SHOP)
    MeterIntervalFactory.create(meter=root, start=at(YESTERDAY, 10), value="10")
    MeterIntervalFactory.create(meter=child, start=at(YESTERDAY, 10), value="9")
    client = _client(_user())

    profile = client.get(f"{BASE}/reports/profile?meter_id={root.id}&day={YESTERDAY}").json()
    balance = client.get(
        f"{BASE}/reports/balance?meter_id={root.id}&date_from={YESTERDAY}&date_to={YESTERDAY}"
    ).json()

    assert len(profile["values"]) == 48
    assert profile["values"][20] == "10.0000"
    assert balance["total"]["loss"] == "1.0000"
    assert balance["total"]["loss_pct"] == "10.00"


def _queries(client: Client, url: str) -> int:
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
        assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


@pytest.mark.parametrize(
    "url", ["/meters", "/reports/tree?resource=el", "/reports/daily?resource=el", "/resources"]
)
def test_списки_и_отчёты_не_делают_n_plus_1(url: str) -> None:
    el = EnergyResourceFactory.create()
    client = _client(_user())

    def build(count: int) -> None:
        root = MeterFactory.create(resource=el)
        for _ in range(count):
            child = MeterFactory.create(resource=el, parent=root, kind=MeterKind.SHOP)
            MeterIntervalFactory.create(meter=child, start=at(YESTERDAY, 10))

    build(2)
    small = _queries(client, BASE + url)
    build(6)
    assert _queries(client, BASE + url) == small
