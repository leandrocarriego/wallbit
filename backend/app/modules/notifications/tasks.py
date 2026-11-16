"""Tareas de notificaciones. Stubs hasta implementar el módulo notifications."""

import structlog
from celery import shared_task

log = structlog.get_logger()


@shared_task(name="notifications.sweep_pending")
def sweep_pending() -> None:
    log.info("notifications.sweep_pending", status="not_implemented")


@shared_task(name="notifications.send_due_reminders")
def send_due_reminders() -> None:
    log.info("notifications.send_due_reminders", status="not_implemented")
