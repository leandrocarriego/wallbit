"""Notification tasks."""

import uuid

import structlog
from celery import shared_task
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.notifications import service
from app.modules.notifications.models import Notification, NotificationStatus

log = structlog.get_logger()


@shared_task(name="notifications.send_close_notification", acks_late=True)
def send_close_notification(notification_id: str) -> str:
    from app.modules.review.service import mark_notified

    with SessionLocal() as session, session.begin():
        notification = service.send(session, uuid.UUID(notification_id), actor="system")
        mark_notified(session, notification, actor="system")
        status = notification.status.value
    log.info("notifications.sent", notification_id=notification_id)
    return status


@shared_task(name="notifications.sweep_pending")
def sweep_pending() -> int:
    """Safety net: send notifications left pending (e.g. a lost message)."""
    with SessionLocal() as session, session.begin():
        pending = list(
            session.scalars(
                select(Notification.id).where(Notification.status == NotificationStatus.PENDING)
            )
        )
    for notification_id in pending:
        send_close_notification.delay(str(notification_id))
    return len(pending)


@shared_task(name="notifications.send_due_reminders")
def send_due_reminders() -> None:
    log.info("notifications.send_due_reminders", status="not_implemented")
