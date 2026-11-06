"""Предикаты прав доступа модуля «Ядро: документы» (django-rules).

Исправление 18.09: до этой правки `can_download` для привязанного документа считал
достаточным «пользователь аутентифицирован» — рассуждение было «раньше presigned-URL
вообще не перепроверялся, значит это перенос прежнего поведения». Вывод неверный:
раньше работало не право, а его отсутствие. Решение 1 ADR 0029 («право проверяется
на каждый запрос байтов») существует именно для того, чтобы закрыть эту дыру, а не
переоформить её под другим именем — воркер занимается на каждое скачивание ради
настоящей проверки, не ради факта входа в систему.

core.documents не знает о сущностях функциональных модулей напрямую (И1) и поэтому
не проверяет «имеет ли пользователь право видеть эту заявку» сам — вызывающий модуль
регистрирует свою проверку видимости через `registry.register_entity_visibility_checker`
при старте (тот же приём, что `core.identity.registry` для профилей). Документ, ни к
чему не привязанный, остаётся строго уполномоченным — только загрузивший и администратор.
"""

from __future__ import annotations

import rules

from src.core.accounts import facade as accounts
from src.core.accounts.models import User
from src.core.documents.models import Document
from src.core.documents.registry import can_view_entity


@rules.predicate
def is_uploader(user: User, document: Document | None = None) -> bool:
    if document is None:
        return False
    return document.uploaded_by == user.id


@rules.predicate
def can_download(user: User, document: Document | None = None) -> bool:
    if document is None:
        return False
    if is_uploader(user, document) or accounts.is_administrator(user):
        return True
    return any(
        can_view_entity(user, link.entity_type, link.entity_id) for link in document.links.all()
    )
