"""Админка модуля «Ядро: документы»."""

from django.contrib import admin
from django.http import HttpRequest
from unfold.admin import ModelAdmin

from src.core.audit.admin import register_history
from src.core.documents.models import (  # type: ignore[attr-defined]
    Document,
    DocumentEvent,
    DocumentLinkEvent,
    DocumentTemplate,
    DocumentTemplateEvent,
    DocumentType,
    DocumentTypeEvent,
)


@admin.register(DocumentType)
class DocumentTypeAdmin(ModelAdmin):
    list_display = ("name", "code", "max_size_bytes", "requires_approval", "is_active")
    list_filter = ("requires_approval", "is_active")
    search_fields = ("name", "code")


@admin.register(DocumentTemplate)
class DocumentTemplateAdmin(ModelAdmin):
    list_display = ("name", "code", "doc_type", "is_active")
    list_filter = ("doc_type", "is_active")
    search_fields = ("name", "code")
    list_select_related = ("doc_type",)


@admin.register(Document)
class DocumentAdmin(ModelAdmin):
    """Только просмотр и список: файлы версионируются, а не правятся и не удаляются
    из интерфейса (старые версии остаются доступными, см. services/versioning.py)."""

    list_display = ("original_name", "doc_type", "version", "uploaded_by", "created_at")
    list_filter = ("doc_type",)
    search_fields = ("original_name", "checksum")
    readonly_fields = [f.name for f in Document._meta.fields]
    list_select_related = ("doc_type",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Document | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Document | None = None) -> bool:
        return False


for _event_model in (
    DocumentTypeEvent,
    DocumentTemplateEvent,
    DocumentEvent,
    DocumentLinkEvent,
):
    register_history(_event_model)
