"""Дашборд django-unfold (config/settings/base.py: UNFOLD["DASHBOARD_CALLBACK"]).

Ключевые показатели — пока заглушки (буквально, без запросов к БД): подключать
реальные цифры имеет смысл вместе с конкретным потребителем отчётности (Metabase,
Фаза 5 по роадмап Фазы 0 ИС, либо отдельный отчётный экран) — тот же принцип, что уже
применяется к facade-функциям модулей («добавляются по мере появления реального
потребителя, а не заранее»), а не потому что запрос за счётчиком дорог.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest


def dashboard_callback(request: HttpRequest, context: dict[str, Any]) -> dict[str, Any]:
    context["kpi_cards"] = [
        {"title": "Пользователи", "value": "—"},
        {"title": "Контрагенты", "value": "—"},
        {"title": "Согласования в работе", "value": "—"},
    ]
    return context
