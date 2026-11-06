"""Публичный интерфейс модуля «Энергоучёт» для других модулей: пока только сид
демо-данных (вызывает команда `seed_demo` приложения после `equipment`)."""

from __future__ import annotations

from src.energy.services.demo import seed_demo

__all__ = ["seed_demo"]
