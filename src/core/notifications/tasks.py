"""Celery-задачи модуля «Ядро: уведомления»: только оркестрация, логика — в services."""

from __future__ import annotations

from uuid import UUID

from celery import shared_task

from src.core.notifications.services import deliver_notification, run_notification_digest


@shared_task(name="core_notifications.send_notification")  # type: ignore[untyped-decorator]
def send_notification_task(notification_id: str) -> None:
    deliver_notification(UUID(notification_id))


@shared_task(name="core_notifications.run_notification_digest")  # type: ignore[untyped-decorator]
def run_notification_digest_task() -> int:
    return len(run_notification_digest())
