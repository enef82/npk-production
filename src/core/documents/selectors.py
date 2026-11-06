"""Запросы на чтение и агрегаты модуля «Ядро: документы»."""

from __future__ import annotations

from uuid import UUID

from django.core.files import File
from django.core.files.storage import default_storage
from django.db import connection
from django.db.models import Exists, OuterRef

from src.core.documents.models import Document, DocumentTemplate

# Просматриваемые в браузере типы (спецификация CRM ИС (IS_ERP, 10-crm) §3.10) — сегодня только PDF.
# Word и Excel сюда осознанно не идут: клиентские библиотеки на реальных инженерных
# документах врут, честный путь — серверная конвертация через Gotenberg, отложенная
# с названным условием пересмотра (шаг 16).
# Значение продублировано с `services.generation.PDF_MIME_TYPE` (не импортируется оттуда —
# `services/__init__.py` сам импортирует этот модуль, `services.generation` → `selectors`
# дал бы циклический импорт), это стандартный MIME-тип IANA, а не решение проекта.
PREVIEWABLE_MIME_TYPES = frozenset({"application/pdf"})

_CURRENT_PER_ROLE_SQL = """
SELECT DISTINCT ON (l.role) d.id
FROM core_documents_documentlink l
JOIN core_documents_document d ON d.id = l.document_id
WHERE l.entity_type = %s AND l.entity_id = %s
ORDER BY l.role, d.version DESC
"""


def get_document(document_id: UUID) -> Document | None:
    return Document.objects.filter(id=document_id).first()


def get_document_template(code: str) -> DocumentTemplate | None:
    return (
        DocumentTemplate.objects.select_related("doc_type")
        .filter(code=code, is_active=True)
        .first()
    )


def get_current_version(entity_type: str, entity_id: UUID, role: str = "") -> Document | None:
    return (
        Document.objects.filter(
            links__entity_type=entity_type, links__entity_id=entity_id, links__role=role
        )
        .order_by("-version")
        .first()
    )


def list_current_for_entity(entity_type: str, entity_id: UUID) -> list[Document]:
    """Текущая (последняя) версия документа на каждую роль, привязанную к сущности."""

    with connection.cursor() as cursor:
        cursor.execute(_CURRENT_PER_ROLE_SQL, [entity_type, str(entity_id)])
        ids = [row[0] for row in cursor.fetchall()]

    documents = {doc.id: doc for doc in Document.objects.filter(id__in=ids)}
    return [documents[doc_id] for doc_id in ids if doc_id in documents]


def list_attachments_for_entity(entity_type: str, entity_id: UUID) -> list[Document]:
    """Актуальные вложения сущности: по одному документу на цепочку версий — её вершине.

    `get_current_version` здесь не годится: он выбирает последнюю версию **в пределах
    роли**, а у всех вложений заявки роль пустая (спецификация CRM ИС (IS_ERP, 10-crm) §3.10), и он вернул
    бы один последний загруженный файл вместо текущей редакции каждого вложения. Вершина
    цепочки — привязанный к сущности документ, который не перекрыт (`supersedes`) другим
    документом, тоже привязанным к этой сущности."""

    linked = Document.objects.filter(links__entity_type=entity_type, links__entity_id=entity_id)
    superseding = Document.objects.filter(
        supersedes_id=OuterRef("pk"),
        links__entity_type=entity_type,
        links__entity_id=entity_id,
    )
    return list(
        linked.exclude(Exists(superseding))
        .select_related("doc_type")
        .order_by("created_at", "id")
        .distinct()
    )


def get_version_chain_ids(document_id: UUID) -> list[UUID]:
    """Все id одной цепочки версий (от корня вниз), начиная с любого её звена."""

    node = Document.objects.filter(id=document_id).only("id", "supersedes_id").first()
    if node is None:
        return []

    seen: set[UUID] = {node.id}
    while node.supersedes_id is not None and node.supersedes_id not in seen:
        parent = Document.objects.filter(id=node.supersedes_id).only("id", "supersedes_id").first()
        if parent is None:
            break
        node = parent
        seen.add(node.id)

    ids: list[UUID] = []
    frontier = [node.id]
    while frontier:
        current = frontier.pop()
        ids.append(current)
        frontier.extend(Document.objects.filter(supersedes_id=current).values_list("id", flat=True))
    return ids


def get_attached_chain_top(entity_type: str, entity_id: UUID, document_id: UUID) -> Document | None:
    """Текущая вершина цепочки версий, к которой относится `document_id`, если эта цепочка
    привязана к сущности. Нужна для «новой редакции»: пользователь может сослаться на любое
    звено, а перекрывать надо актуальное."""

    chain_ids = set(get_version_chain_ids(document_id))
    if not chain_ids:
        return None
    for document in list_attachments_for_entity(entity_type, entity_id):
        if document.id in chain_ids:
            return document
    return None


def list_versions(document_id: UUID) -> list[Document]:
    """Все версии документа (включая переданную), новые сверху — «предыдущие доступны»
    (спецификация CRM ИС (IS_ERP, 10-crm) §3.10)."""

    chain_ids = get_version_chain_ids(document_id)
    if not chain_ids:
        return []
    return list(
        Document.objects.filter(id__in=chain_ids)
        .select_related("doc_type")
        .order_by("-version", "-created_at")
    )


def is_previewable(document: Document) -> bool:
    return document.mime_type in PREVIEWABLE_MIME_TYPES


def get_download_url(document: Document, *, disposition: str | None = None) -> str:
    """Ссылка ведёт на собственный эндпоинт Django (`/{document_id}/download`,
    `api.routers.download`), не на presigned S3-URL (docs/adr/0029-prod-kontur.md, п. 1).

    До этой правки ссылка сама была «билетом»: `can_download` проверялся один раз, на
    выдачу (`/link`), а дальше presigned-URL работал `DOCUMENTS_URL_TTL_SECONDS` вперёд
    независимо от того, что случится с правом доступа за это время. Теперь ссылка —
    обычный путь API, а право проверяется на каждый запрос байтов той же сессией, что
    и весь остальной API — TTL для самой ссылки больше не нужен, поэтому параметра
    `ttl_seconds` здесь больше нет (вызывающие продолжают считать `expires_at` сами,
    это осталось в схеме ответа как метаданные, не как срок годности ссылки).

    `disposition` — `"inline"` (просмотр в браузере) или `"attachment"` (скачивание).
    По умолчанию `None` — `api.routers.download` отдаёт `inline` (умолчание Django
    `FileResponse`) с настоящим именем файла. Решает, каким вложениям нужно
    принудительное скачивание, вызывающий модуль (`is_previewable`), не эта функция."""

    url = f"/api/v1/documents/{document.id}/download"
    if disposition is not None:
        url = f"{url}?disposition={disposition}"
    return url


def open_document_file(document: Document) -> File[bytes]:
    """Открывает файл документа на чтение для потоковой отдачи (`FileResponse` в
    `api.routers.download`) — не читает его целиком в память (docs/adr/0029-prod-kontur.md,
    п. 1: честная цена отдачи через Django — воркер, а не память)."""

    return default_storage.open(document.file.name, "rb")
