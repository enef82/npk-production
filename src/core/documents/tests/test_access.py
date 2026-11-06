"""Доступ к файлу: собственный эндпоинт Django, приватность бакета, права на скачивание.

docs/adr/0029-prod-kontur.md, п. 1: ссылка на файл — путь на `/{document_id}/download`,
не presigned S3-URL. Право проверяется на каждый запрос байтов тем же эндпоинтом,
поэтому тесты ниже проверяют это через реальный HTTP-запрос к `download`, а не через
разбор параметров подписи, как было до этой правки."""

from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import httpx
import pytest
from django.conf import settings
from django.core.signals import request_finished
from django.db import close_old_connections
from django.test import Client

from src.core.accounts.tests.factories import UserFactory
from src.core.documents.models import DocumentLink
from src.core.documents.registry import register_entity_visibility_checker
from src.core.documents.rules import can_download
from src.core.documents.selectors import get_download_url, is_previewable
from src.core.documents.tests.factories import PDF_CONTENT, DocumentFactory


def _close_streaming_response(response: object) -> bytes:
    """`FileResponse` — потоковый ответ: тестовый `Client` закрывает такие лениво,
    через `closing_iterator_wrapper` на `streaming_content` (`django/test/client.py`,
    `ClientHandler.__call__`), а не сразу, как обычные ответы. У обычных ответов
    Django на время `response.close()` отключает `close_old_connections` от
    `request_finished` и включает обратно — у потоковых этой защиты нет, и наивное
    ручное закрытие рвёт соединение с БД, которым ещё пользуется тест (реальный
    WSGI-сервер это переживает, потому что запрос там уже закончен; тест — нет).
    Здесь та же защита воспроизведена вручную вокруг чтения и закрытия."""

    request_finished.disconnect(close_old_connections)
    try:
        content = b"".join(response.streaming_content)  # type: ignore[attr-defined]
        response.close()  # type: ignore[attr-defined]
    finally:
        request_finished.connect(close_old_connections)
    return content


@pytest.mark.django_db
def test_pdf_просматриваемый_остальное_нет() -> None:
    """Шаг 16 (спец. CRM ИС §3.10): просматривается сегодня только PDF —
    Word и Excel осознанно вне списка, решение зафиксировано в спеке."""

    pdf = DocumentFactory(mime_type="application/pdf")
    dwg = DocumentFactory(mime_type="image/vnd.dwg")

    assert is_previewable(pdf) is True  # type: ignore[arg-type]
    assert is_previewable(dwg) is False  # type: ignore[arg-type]


@pytest.mark.django_db
def test_ссылка_на_pdf_несёт_disposition_показать_в_запросе() -> None:
    document = DocumentFactory(mime_type="application/pdf", original_name="komplekt-pd.pdf")

    url = get_download_url(document, disposition="inline")  # type: ignore[arg-type]

    assert parse_qs(urlparse(url).query)["disposition"] == ["inline"]


@pytest.mark.django_db
def test_ссылка_на_остальные_типы_несёт_disposition_скачать_в_запросе() -> None:
    document = DocumentFactory(mime_type="image/vnd.dwg", original_name="shema.dwg")

    url = get_download_url(document, disposition="attachment")  # type: ignore[arg-type]

    assert parse_qs(urlparse(url).query)["disposition"] == ["attachment"]


@pytest.mark.django_db
def test_без_disposition_ссылка_без_параметра_disposition() -> None:
    """Существующие вызывающие (генерация КП) поведение не меняют: `disposition=None` —
    ссылка без параметра `disposition` вовсе, как до этой правки."""

    document = DocumentFactory()

    url = get_download_url(document)  # type: ignore[arg-type]

    assert "disposition" not in parse_qs(urlparse(url).query)


@pytest.mark.django_db
def test_прямой_публичный_доступ_к_бакету_закрыт() -> None:
    """MinIO не публикуется наружу (docs/adr/0029-prod-kontur.md, п. 1), но проверка
    приватности бакета не зависит от того, кто отдаёт файл браузеру — она про то,
    что сам объект в хранилище не читается кем угодно, минуя приложение вовсе."""

    document = DocumentFactory()
    file_name = document.file.name  # type: ignore[attr-defined]

    raw_url = f"{settings.AWS_S3_ENDPOINT_URL}/{settings.AWS_STORAGE_BUCKET_NAME}/{file_name}"

    assert httpx.get(raw_url).status_code == 403


@pytest.mark.django_db
def test_загрузивший_скачивает_файл_через_download_и_получает_те_же_байты(
    client: Client,
) -> None:
    owner = UserFactory()
    owner_id = owner.id  # type: ignore[attr-defined]
    document = DocumentFactory(uploaded_by=owner_id)
    document_id = document.id  # type: ignore[attr-defined]

    client.force_login(owner)  # type: ignore[arg-type]
    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response.status_code == 200
    assert _close_streaming_response(response) == PDF_CONTENT


@pytest.mark.django_db
def test_чужой_пользователь_не_может_скачать_байты_через_download(client: Client) -> None:
    owner = UserFactory()
    owner_id = owner.id  # type: ignore[attr-defined]
    stranger = UserFactory()
    document = DocumentFactory(uploaded_by=owner_id)
    document_id = document.id  # type: ignore[attr-defined]

    client.force_login(stranger)  # type: ignore[arg-type]
    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response.status_code == 403


@pytest.mark.django_db
def test_download_с_disposition_inline_отдаёт_заголовок_content_disposition(
    client: Client,
) -> None:
    owner = UserFactory()
    owner_id = owner.id  # type: ignore[attr-defined]
    document = DocumentFactory(
        uploaded_by=owner_id, mime_type="application/pdf", original_name="komplekt-pd.pdf"
    )
    document_id = document.id  # type: ignore[attr-defined]

    client.force_login(owner)  # type: ignore[arg-type]
    response = client.get(f"/api/v1/documents/{document_id}/download", {"disposition": "inline"})

    assert response["Content-Disposition"].startswith("inline;")
    assert "komplekt-pd.pdf" in response["Content-Disposition"]
    _close_streaming_response(response)


@pytest.mark.django_db
def test_download_без_disposition_отдаёт_inline_с_настоящим_именем_файла(
    client: Client,
) -> None:
    """`FileResponse` без явного `disposition` не остаётся без заголовка вовсе —
    Django сам ставит `inline` и имя (умолчание `FileResponse.as_attachment=False`).
    Важно здесь то, что имя — `original_name` документа, а не ключ в хранилище
    (обычно UUID): без `filename=` в `FileResponse` браузер увидел бы имя вида
    `a1b2c3d4-....pdf` вместо того, что пользователь загрузил."""

    owner = UserFactory()
    owner_id = owner.id  # type: ignore[attr-defined]
    document = DocumentFactory(uploaded_by=owner_id, original_name="komplekt-pd.pdf")
    document_id = document.id  # type: ignore[attr-defined]

    client.force_login(owner)  # type: ignore[arg-type]
    response = client.get(f"/api/v1/documents/{document_id}/download")

    assert response["Content-Disposition"].startswith("inline;")
    assert "komplekt-pd.pdf" in response["Content-Disposition"]
    _close_streaming_response(response)


@pytest.mark.django_db
def test_загрузивший_может_скачать_свой_файл() -> None:
    user = UserFactory()
    user_id = user.id  # type: ignore[attr-defined]
    document = DocumentFactory(uploaded_by=user_id)

    assert can_download(user, document) is True


@pytest.mark.django_db
def test_чужой_пользователь_не_может_скачать_файл() -> None:
    user = UserFactory()
    document = DocumentFactory()

    assert can_download(user, document) is False


@pytest.mark.django_db
def test_привязанный_документ_без_зарегистрированного_чекера_недоступен_постороннему() -> None:
    """core.documents не знает entity_type функциональных модулей (докстринг rules.py) —
    привязка к типу, для которого никто не зарегистрировался, не должна молча открывать
    доступ. Исправление 18.09: до этой правки любая привязка вообще («хоть к чему-то»)
    открывала документ любому аутентифицированному — это и была дыра."""

    user = UserFactory()
    document = DocumentFactory()
    DocumentLink.objects.create(
        document=document,  # type: ignore[misc]
        entity_type="unregistered.entity",
        entity_id=uuid4(),
    )

    assert can_download(user, document) is False


@pytest.mark.django_db
def test_registry_делегирует_зарегистрированному_чекеру_видимости() -> None:
    user = UserFactory()
    visible_entity_id = uuid4()
    hidden_entity_id = uuid4()
    visible_document = DocumentFactory()
    hidden_document = DocumentFactory()
    DocumentLink.objects.create(
        document=visible_document,  # type: ignore[misc]
        entity_type="test.entity",
        entity_id=visible_entity_id,
    )
    DocumentLink.objects.create(
        document=hidden_document,  # type: ignore[misc]
        entity_type="test.entity",
        entity_id=hidden_entity_id,
    )

    register_entity_visibility_checker("test.entity", lambda u, eid: eid == visible_entity_id)
    try:
        assert can_download(user, visible_document) is True
        assert can_download(user, hidden_document) is False
    finally:
        register_entity_visibility_checker("test.entity", lambda u, eid: False)


@pytest.mark.django_db
def test_администратор_может_скачать_любой_файл() -> None:
    admin = UserFactory(is_superuser=True)
    document = DocumentFactory()

    assert can_download(admin, document) is True


@pytest.mark.django_db
def test_нельзя_скачать_файл_без_прав(client: Client) -> None:
    owner = UserFactory()
    owner_id = owner.id  # type: ignore[attr-defined]
    stranger = UserFactory()
    document = DocumentFactory(uploaded_by=owner_id)
    document_id = document.id  # type: ignore[attr-defined]

    client.force_login(stranger)  # type: ignore[arg-type]
    response = client.get(f"/api/v1/documents/{document_id}/link")

    assert response.status_code == 403


@pytest.mark.django_db
def test_загрузивший_получает_ссылку_через_api(client: Client) -> None:
    owner = UserFactory()
    owner_id = owner.id  # type: ignore[attr-defined]
    document = DocumentFactory(uploaded_by=owner_id)
    document_id = document.id  # type: ignore[attr-defined]

    client.force_login(owner)  # type: ignore[arg-type]
    response = client.get(f"/api/v1/documents/{document_id}/link")

    assert response.status_code == 200
    assert "url" in response.json()
