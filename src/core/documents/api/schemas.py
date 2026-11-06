"""Pydantic-схемы входа и выхода API модуля «Ядро: документы»."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from ninja import Schema


class DocumentOut(Schema):
    id: UUID
    original_name: str
    size_bytes: int
    mime_type: str
    checksum: str
    doc_type_id: UUID
    version: int
    uploaded_by: UUID
    created_at: datetime


class DownloadLinkOut(Schema):
    url: str
    expires_at: datetime
