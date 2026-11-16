"""Close tasks. Messages carry ids only; every task reads the current state from the DB."""

import uuid

import structlog
from celery import shared_task
from sqlalchemy import select

from app.core.db import SessionLocal
from app.modules.closing import service
from app.modules.closing.models import PeriodClose
from app.modules.demo.service import today

log = structlog.get_logger()
SYSTEM = "system"


@shared_task(name="closing.start_period_close")
def start_period_close(period: str | None = None) -> str:
    with SessionLocal() as session, session.begin():
        period = period or service.previous_period(today(session))
        closes = service.start_period_close(session, period, actor=SYSTEM)
    log.info("closing.start_period_close", period=period, clients=len(closes))
    return period


@shared_task(name="closing.compute_client_close", acks_late=True)
def compute_client_close(client_id: str, period: str) -> str:
    return _compute(client_id, period)


@shared_task(name="recompute.recompute_client_close", acks_late=True)
def recompute_client_close(client_id: str, period: str) -> str:
    return _compute(client_id, period)


def _compute(client_id: str, period: str) -> str:
    with SessionLocal() as session, session.begin():
        close = service.compute_client_close(
            session, uuid.UUID(client_id), period, today=today(session), actor=SYSTEM
        )
        status = close.status.value
    log.info("closing.computed", client_id=client_id, period=period, status=status)
    return status


@shared_task(name="closing.expire_pending_questions")
def expire_pending_questions(period: str | None = None) -> int:
    with SessionLocal() as session, session.begin():
        period = period or service.previous_period(today(session))
        return service.expire_pending_questions(session, period, actor=SYSTEM)


@shared_task(name="recompute.sweep_dirty_closes")
def sweep_dirty_closes() -> int:
    """Safety net: recompute any close left dirty (e.g. a message lost between commit and send)."""
    with SessionLocal() as session, session.begin():
        dirty = session.scalars(
            select(PeriodClose).where(
                PeriodClose.dirty.is_(True), PeriodClose.status.not_in(service.FROZEN)
            )
        ).all()
        for close in dirty:
            service.enqueue_recompute(session, close.client_id, close.period)
    return len(dirty)


@shared_task(name="recompute.ping")
def ping() -> str:
    return "pong"
