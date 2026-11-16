"""Accountant console endpoints for the monthly close."""

import uuid
from collections import Counter
from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.errors import NotFoundError
from app.core.http import DbSession
from app.core.periods import local_date
from app.modules.alerts.engine import CloseStatus
from app.modules.audit.models import AuditEvent
from app.modules.classification.models import MovementClassification
from app.modules.classification.service import counterparty_keys
from app.modules.clients.models import Client
from app.modules.closing.models import CloseAlert, PeriodClose
from app.modules.closing.schemas import (
    AlertOut,
    AuditRow,
    CloseDetail,
    Inbox,
    InboxRow,
    InvoiceRow,
    MovementOut,
)
from app.modules.demo.service import today
from app.modules.ingestion.models import Movement
from app.modules.invoices.models import Invoice

router = APIRouter(prefix="/api/v1/period-closes", tags=["accountant"])

SEVERITY_ORDER = {"blocking": 0, "waiting": 1, "info": 2}
STATUS_ORDER = {
    CloseStatus.IN_REVIEW: 0,
    CloseStatus.PENDING_DATA: 1,
    CloseStatus.READY: 2,
    CloseStatus.APPROVED: 3,
    CloseStatus.NOTIFIED: 4,
}


def _alert_out(a: CloseAlert) -> AlertOut:
    return AlertOut(
        id=a.id,
        key=a.key,
        type=a.type,
        severity=a.severity,
        title=a.title,
        detail=a.detail,
        subject_id=a.subject_id,
        amount=a.amount,
        status=a.status,
    )


def _alerts(session: DbSession, close_id: uuid.UUID) -> list[AlertOut]:
    rows = session.scalars(
        select(CloseAlert).where(CloseAlert.close_id == close_id, CloseAlert.present.is_(True))
    )
    return sorted((_alert_out(a) for a in rows), key=lambda a: SEVERITY_ORDER[a.severity])


@router.get("")
def inbox(session: DbSession, period: str = Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")) -> Inbox:
    closes = list(session.scalars(select(PeriodClose).where(PeriodClose.period == period)))
    clients = {c.id: c for c in session.scalars(select(Client))}
    rows = []
    for pc in closes:
        c = clients[pc.client_id]
        r = pc.result or {}
        rows.append(
            InboxRow(
                close_id=pc.id,
                client_id=c.id,
                full_name=c.full_name,
                cuit=c.cuit,
                category=c.category,
                status=pc.status,
                invoiced_usd=Decimal(r["invoiced_by_currency"].get("USD", "0")) if r else None,
                collected_usd=Decimal(r["collected_usd"]) if r else None,
                cap_usage_pct=Decimal(r["cap_usage_pct"]) if r else None,
                alerts=_alerts(session, pc.id),
            )
        )
    rows.sort(key=lambda row: (STATUS_ORDER[row.status], -len(row.alerts), row.full_name))
    counts = Counter(row.status for row in rows)
    return Inbox(
        period=period,
        started=bool(closes),
        today=today(session),
        counts={s: counts.get(s, 0) for s in CloseStatus},
        rows=rows,
    )


@router.get("/{close_id}")
def detail(close_id: uuid.UUID, session: DbSession) -> CloseDetail:
    pc = session.get(PeriodClose, close_id)
    if pc is None:
        raise NotFoundError("close_not_found", "No existe ese cierre.")
    client = session.get(Client, pc.client_id)
    assert client is not None
    keys = counterparty_keys(session)
    invoices = {
        i.id: i
        for i in session.scalars(
            select(Invoice).where(Invoice.client_id == client.id, Invoice.period == pc.period)
        )
    }
    classified = {
        c.movement_id: c
        for c in session.scalars(
            select(MovementClassification).where(
                MovementClassification.client_id == client.id,
                MovementClassification.period == pc.period,
            )
        )
    }
    movements = []
    for m in session.scalars(
        select(Movement)
        .where(Movement.client_id == client.id, Movement.period == pc.period)
        .order_by(Movement.occurred_at)
    ):
        c = classified.get(m.id)
        invoice = session.get(Invoice, c.invoice_id) if c and c.invoice_id else None
        movements.append(
            MovementOut(
                id=m.id,
                occurred_on=local_date(m.occurred_at),
                type=m.type.value,
                direction=m.direction.value,
                amount=m.amount,
                currency=m.currency,
                counterparty=keys[m.counterparty_id][1] if m.counterparty_id in keys else None,
                memo=m.memo,
                category=c.category if c else None,
                source=c.source if c else None,
                invoice_number=invoice.number if invoice else None,
                suggestion=c.suggestion if c else None,
                trace=c.trace if c else [],
            )
        )
    history = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.client_id == client.id)
        .order_by(AuditEvent.created_at.desc())
        .limit(50)
    )
    return CloseDetail(
        close_id=pc.id,
        period=pc.period,
        status=pc.status,
        version=pc.version,
        computed_at=pc.computed_at,
        engine_version=pc.engine_version,
        params_name=pc.params_name,
        client={
            "id": str(client.id),
            "full_name": client.full_name,
            "cuit": client.cuit,
            "activity": client.activity,
            "category": client.category,
            "jurisdiction": client.jurisdiction,
        },
        result=pc.result,
        alerts=_alerts(session, pc.id),
        movements=movements,
        invoices=[
            InvoiceRow(
                id=i.id,
                number=i.number,
                issued_on=i.issued_on,
                customer_name=i.customer_name,
                amount=i.amount,
                currency=i.currency,
                fx_rate_ars=i.fx_rate_ars,
                source=i.source.value,
                received_at=i.received_at,
            )
            for i in sorted(invoices.values(), key=lambda i: i.number)
        ],
        history=[
            AuditRow(created_at=e.created_at, actor=e.actor, action=e.action, after=e.after)
            for e in history
        ],
    )
