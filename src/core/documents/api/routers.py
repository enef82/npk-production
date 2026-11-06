"""Эндпоинты django-ninja модуля «Ядро: документы»."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.http import FileResponse, HttpRequest
from ninja import File, Form, Router
from ninja.files import UploadedFile

from src.core.accounts.models import User
from src.core.common.exceptions import PermissionDenied
from src.core.documents import rules as documents_rules
from src.core.documents import selectors
from src.core.documents.services.upload import DocumentUploadDTO, upload_document

from .schemas import DocumentOut, DownloadLinkOut

router = Router(tags=["documents"])


class AuthenticatedHttpRequest(HttpRequest):
    """`request.auth` — атрибут, который проставляет django-ninja при аутентификации
    (`NinjaAPI(auth=django_auth)`); в стандартном стабе HttpRequest его нет."""

    auth: User


@router.post("/upload", response=DocumentOut)
def upload(
    request: AuthenticatedHttpRequest,
    file: UploadedFile = File(...),
    doc_type_code: str = Form(...),
    entity_type: str = Form(""),
    entity_id: UUID | None = Form(None),
    role: str = Form(""),
) -> DocumentOut:
    document = upload_document(
        DocumentUploadDTO(
            file=file,
            doc_type_code=doc_type_code,
            uploaded_by=request.auth.id,
            entity_type=entity_type,
            entity_id=entity_id,
            role=role,
        )
    )
    return document  # type: ignore[return-value]


@router.get("/{document_id}/link", response=DownloadLinkOut)
def get_link(request: AuthenticatedHttpRequest, document_id: UUID) -> DownloadLinkOut:
    document = selectors.get_document(document_id)
    if document is None:
        # 403, а не 404: не подтверждаем посторонним само существование document_id.
        raise PermissionDenied("Документ не найден или недоступен.")
    if not documents_rules.can_download(request.auth, document):
        raise PermissionDenied("Недостаточно прав для скачивания документа.")

    ttl = settings.DOCUMENTS_URL_TTL_SECONDS
    url = selectors.get_download_url(document)
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    return DownloadLinkOut(url=url, expires_at=expires_at)


@router.get("/{document_id}/download")
def download(
    request: AuthenticatedHttpRequest, document_id: UUID, disposition: str | None = None
) -> FileResponse:
    """Отдаёт содержимое документа потоком (docs/adr/0029-prod-kontur.md, п. 1) —
    право проверяется здесь, на каждый запрос байтов, а не только на выдачу `/link`.
    `disposition` — `"inline"`/`"attachment"`, тот же смысл, что и у параметра
    `get_download_url`; без него — тот же `inline` (умолчание `FileResponse`), но
    с настоящим именем файла (`original_name`), а не именем ключа в хранилище."""

    document = selectors.get_document(document_id)
    if document is None:
        raise PermissionDenied("Документ не найден или недоступен.")
    if not documents_rules.can_download(request.auth, document):
        raise PermissionDenied("Недостаточно прав для скачивания документа.")

    # filename= — не украшение: без него FileResponse угадывает имя по ключу
    # хранилища (`document.file.name`, обычно UUID), а не по тому, что видел
    # пользователь при загрузке. Django сам кодирует не-ASCII (кириллицу) в
    # Content-Disposition по RFC 5987 — отдельный хелпер для этого не нужен.
    return FileResponse(
        selectors.open_document_file(document),
        content_type=document.mime_type,
        filename=document.original_name,
        as_attachment=(disposition == "attachment"),
    )


@router.get("/entity/{entity_type}/{entity_id}", response=list[DocumentOut])
def list_for_entity(
    request: AuthenticatedHttpRequest, entity_type: str, entity_id: UUID
) -> list[DocumentOut]:
    return selectors.list_current_for_entity(entity_type, entity_id)  # type: ignore[return-value]
