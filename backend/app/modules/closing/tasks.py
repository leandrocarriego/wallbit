"""Tareas del cierre. Stubs: la lógica llega con el módulo closing (ver STATUS.md)."""

import structlog
from celery import shared_task

log = structlog.get_logger()


@shared_task(name="closing.start_period_close")
def start_period_close(period: str | None = None) -> None:
    log.info("closing.start_period_close", period=period, status="not_implemented")


@shared_task(name="closing.expire_pending_confirmations")
def expire_pending_confirmations() -> None:
    log.info("closing.expire_pending_confirmations", status="not_implemented")


@shared_task(name="recompute.sweep_dirty_closes")
def sweep_dirty_closes() -> None:
    log.info("recompute.sweep_dirty_closes", status="not_implemented")


@shared_task(name="recompute.ping")
def ping() -> str:
    return "pong"
