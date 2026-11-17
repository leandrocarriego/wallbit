"""Day-1 consolidation of the monthly close (decision 20) and the day-5 deadline.

Every function here runs inside the caller's transaction and writes its audit event there.
Celery tasks are enqueued with `enqueue_after_commit`, never before the data is committed.
"""

import hashlib
import json
import uuid
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.after_commit import enqueue_after_commit
from app.core.locks import lock_client
from app.core.periods import first_day, period_of, shift
from app.modules.alerts import engine as alerts_engine
from app.modules.alerts.engine import CloseStatus
from app.modules.audit.service import record
from app.modules.classification import engine as cls_engine
from app.modules.classification.models import MovementClassification
from app.modules.classification.service import counterparty_keys, reclassify, to_engine_movement
from app.modules.clients.models import Client
from app.modules.closing.models import AlertStatus, CloseAlert, PeriodClose
from app.modules.ingestion.models import Movement
from app.modules.invoices.models import Invoice
from app.modules.parameters.models import TaxParameterSet
from app.modules.prompts.models import PromptKind, PromptStatus, UserPrompt
from app.modules.tax_engine import engine as tax_engine

FROZEN = (CloseStatus.APPROVED, CloseStatus.NOTIFIED)
ANSWER_DEADLINE_DAY = 5

Enqueue = Callable[[Session, uuid.UUID, str], None]


def enqueue_compute(session: Session, client_id: uuid.UUID, period: str) -> None:
    enqueue_after_commit(session, "closing.compute_client_close", str(client_id), period)


def enqueue_recompute(session: Session, client_id: uuid.UUID, period: str) -> None:
    enqueue_after_commit(session, "recompute.recompute_client_close", str(client_id), period)


def deadline_passed(period: str, today: date) -> bool:
    return today > first_day(shift(period, 1)).replace(day=ANSWER_DEADLINE_DAY)


def start_period_close(
    session: Session, period: str, *, actor: str, enqueue: Enqueue = enqueue_compute
) -> list[PeriodClose]:
    """Create one close per active client (idempotent) and schedule its computation."""
    clients = [c for c in session.scalars(select(Client)) if c.is_active]
    existing = {
        pc.client_id: pc
        for pc in session.scalars(select(PeriodClose).where(PeriodClose.period == period))
    }
    closes = []
    for client in clients:
        close = existing.get(client.id)
        if close is None:
            close = PeriodClose(client_id=client.id, period=period, status=CloseStatus.PENDING_DATA)
            session.add(close)
        closes.append(close)
    session.flush()
    record(
        session,
        actor=actor,
        action="close.period_started",
        entity_type="period",
        period=period,
        after={"clients": len(closes)},
    )
    for close in closes:
        if close.status not in FROZEN:
            enqueue(session, close.client_id, period)
    return closes


def mark_dirty(session: Session, client_id: uuid.UUID, period: str) -> PeriodClose | None:
    """Called by anything that changes a close's inputs. Schedules a recompute after commit."""
    close = session.scalars(
        select(PeriodClose).where(PeriodClose.client_id == client_id, PeriodClose.period == period)
    ).first()
    if close is None or close.status in FROZEN:
        return None
    close.dirty = True
    enqueue_recompute(session, client_id, period)
    return close


def compute_client_close(
    session: Session, client_id: uuid.UUID, period: str, *, today: date, actor: str
) -> PeriodClose:
    lock_client(session, client_id)
    close = session.scalars(
        select(PeriodClose)
        .where(PeriodClose.client_id == client_id, PeriodClose.period == period)
        .with_for_update()
    ).one()
    if close.status in FROZEN:
        return close  # only a reopen (with reason) changes an approved close
    client = session.get(Client, client_id)
    assert client is not None and client.category is not None

    now = datetime.now(UTC)
    if deadline_passed(period, today):
        _expire_questions(session, client.id, period, now)
    reclassify(session, client, period, actor=actor, now=now)
    keys = counterparty_keys(session)
    movements = list(
        session.scalars(
            select(Movement).where(Movement.client_id == client.id, Movement.period == period)
        )
    )
    rows = {
        c.movement_id: c
        for c in session.scalars(
            select(MovementClassification).where(
                MovementClassification.client_id == client.id,
                MovementClassification.period == period,
            )
        )
    }
    engine_movements = [to_engine_movement(m, keys) for m in movements]
    classifications = [_classification(rows[m.id]) for m in movements]
    invoices = list(
        session.scalars(
            select(Invoice).where(Invoice.client_id == client.id, Invoice.period == period)
        )
    )
    params = _params_for(session, period)

    result = tax_engine.compute_close(
        tax_engine.CloseInput(
            period=period,
            category=client.category,
            activity_type=client.activity_type,
            invoices=[
                tax_engine.InvoiceAmount(i.number, i.amount, i.currency, i.fx_rate_ars)
                for i in sorted(invoices, key=lambda i: i.number)
            ],
            prior_11_months_ars=_invoiced_ars(session, client.id, shift(period, -11), period),
            params=params,
        )
    )
    alerts = alerts_engine.evaluate_alerts(
        alerts_engine.AlertInput(
            movements=engine_movements,
            classifications=classifications,
            invoices=[
                cls_engine.InvoiceIn(
                    str(i.id),
                    i.number,
                    keys[i.counterparty_id][0] if i.counterparty_id in keys else None,
                    i.amount,
                    i.currency,
                    i.issued_on,
                )
                for i in invoices
            ],
            result=result,
            prior_months_invoiced_ars=[
                _invoiced_ars(session, client.id, shift(period, -n), shift(period, -n + 1))
                for n in (3, 2, 1)
            ],
            answer_deadline_passed=deadline_passed(period, today),
        )
    )

    resolved = _store_alerts(session, close, alerts)
    collected = sum(
        (m.amount for m, c in zip(movements, classifications, strict=True) if c.billable),
        Decimal("0"),
    )
    status = alerts_engine.derive_status(alerts, resolved)
    inputs_hash = _hash(engine_movements, classifications, invoices, params.name, client)

    changed = inputs_hash != close.inputs_hash or status is not close.status
    close.status = status
    close.result = _result_json(result, collected)
    close.engine_version = result.engine_version
    close.params_name = result.params_name
    close.inputs_hash = inputs_hash
    close.computed_at = now
    close.dirty = False
    if changed:
        close.version += 1
    record(
        session,
        actor=actor,
        action="close.computed",
        entity_type="period_close",
        entity_id=close.id,
        client_id=client.id,
        period=period,
        after={
            "status": status.value,
            "version": close.version,
            "inputs_hash": inputs_hash,
            "engine_version": result.engine_version,
            "params": result.params_name,
            "alerts": sorted(a.key for a in alerts),
        },
    )
    return close


def expire_pending_questions(session: Session, period: str, *, actor: str) -> int:
    """Day 5: unanswered "¿Quién es?" questions go to the accountant.

    Only marks the open closes dirty: each recompute expires its client's questions under the
    client lock. Expiring them all here, in one transaction, deadlocked with a user answering
    at the same time (prompt row → close row here, close row → prompt row there).
    """
    pending = session.scalar(
        select(func.count())
        .select_from(UserPrompt)
        .where(
            UserPrompt.period == period,
            UserPrompt.kind == PromptKind.WHO_IS,
            UserPrompt.status == PromptStatus.OPEN,
        )
    )
    record(
        session,
        actor=actor,
        action="prompts.expired",
        entity_type="period",
        period=period,
        after={"expired": pending or 0},
    )
    # The deadline changes every open close (unclassified becomes blocking).
    for client_id in sorted(_open_closes(session, period)):
        mark_dirty(session, client_id, period)
    return pending or 0


def _expire_questions(session: Session, client_id: uuid.UUID, period: str, now: datetime) -> None:
    for p in session.scalars(
        select(UserPrompt).where(
            UserPrompt.client_id == client_id,
            UserPrompt.period == period,
            UserPrompt.kind == PromptKind.WHO_IS,
            UserPrompt.status == PromptStatus.OPEN,
        )
    ):
        p.status = PromptStatus.EXPIRED
        p.closed_at = now


def previous_period(today: date) -> str:
    return shift(period_of(today), -1)


def _open_closes(session: Session, period: str) -> set[uuid.UUID]:
    return set(
        session.scalars(
            select(PeriodClose.client_id).where(
                PeriodClose.period == period, PeriodClose.status.not_in(FROZEN)
            )
        )
    )


def _classification(row: MovementClassification) -> cls_engine.Classification:
    return cls_engine.Classification(
        movement_id=str(row.movement_id),
        category=row.category,
        source=row.source,
        rule_id=str(row.rule_id) if row.rule_id else None,
        invoice_id=str(row.invoice_id) if row.invoice_id else None,
        declaration_id=str(row.declaration_id) if row.declaration_id else None,
    )


def _params_for(session: Session, period: str) -> tax_engine.TaxParams:
    day = first_day(period)
    row = session.scalars(
        select(TaxParameterSet)
        .where(TaxParameterSet.valid_from <= day)
        .where((TaxParameterSet.valid_to.is_(None)) | (TaxParameterSet.valid_to > day))
        .order_by(TaxParameterSet.valid_from.desc())
    ).first()
    if row is None:
        raise RuntimeError(f"No hay parámetros fiscales vigentes para {period}")
    return tax_engine.TaxParams(
        name=row.name,
        categories=[
            tax_engine.CategoryParams(
                c.category, c.annual_cap_ars, c.monthly_fee_services_ars, c.monthly_fee_goods_ars
            )
            for c in row.categories
        ],
        regime_max_annual_ars=row.regime_max_annual_ars,
    )


def _invoiced_ars(
    session: Session, client_id: uuid.UUID, from_period: str, to_period: str
) -> Decimal:
    """Invoiced ARS in [from_period, to_period), from the ARCA invoices."""
    invoices = session.scalars(
        select(Invoice).where(
            Invoice.client_id == client_id,
            Invoice.period >= from_period,
            Invoice.period < to_period,
        )
    )
    return sum((tax_engine.money(i.amount * i.fx_rate_ars) for i in invoices), Decimal("0"))


def _store_alerts(
    session: Session, close: PeriodClose, alerts: list[alerts_engine.Alert]
) -> frozenset[str]:
    """Upsert alerts by key, keep resolutions, flag the ones that disappeared."""
    stored = {
        a.key: a for a in session.scalars(select(CloseAlert).where(CloseAlert.close_id == close.id))
    }
    seen = set()
    for alert in alerts:
        seen.add(alert.key)
        row = stored.get(alert.key) or CloseAlert(
            close_id=close.id, key=alert.key, status=AlertStatus.OPEN
        )
        row.type = alert.type
        row.severity = alert.severity
        row.title = alert.title
        row.detail = alert.detail
        row.subject_id = uuid.UUID(alert.subject_id) if alert.subject_id else None
        row.amount = alert.amount
        row.present = True
        session.add(row)
    for key, row in stored.items():
        if key not in seen:
            row.present = False
    session.flush()
    return frozenset(k for k, r in stored.items() if r.status is AlertStatus.RESOLVED)


def _hash(
    movements: list[cls_engine.MovementIn],
    classifications: list[cls_engine.Classification],
    invoices: list[Invoice],
    params_name: str,
    client: Client,
) -> str:
    payload = {
        "client": [str(client.id), client.category, client.activity_type],
        "params": params_name,
        "engine": tax_engine.ENGINE_VERSION,
        "movements": sorted(
            [m.id, str(m.amount), c.category.value, c.invoice_id or ""]
            for m, c in zip(movements, classifications, strict=True)
        ),
        "invoices": sorted([str(i.id), str(i.amount), str(i.fx_rate_ars)] for i in invoices),
    }
    raw = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _result_json(r: tax_engine.CloseResult, collected_usd: Decimal) -> dict[str, Any]:
    return {
        "invoiced_by_currency": {k: str(v) for k, v in r.invoiced_by_currency.items()},
        "invoiced_ars": str(r.invoiced_ars),
        "collected_usd": str(collected_usd),
        "rolling_12m_ars": str(r.rolling_12m_ars),
        "category": r.category.value,
        "category_cap_ars": str(r.category_cap_ars),
        "cap_usage_pct": str(r.cap_usage_pct),
        "required_category": r.required_category.value if r.required_category else None,
        "exceeds_category": r.exceeds_category,
        "exceeds_regime": r.exceeds_regime,
        "monthly_fee_ars": str(r.monthly_fee_ars),
        "due_date": r.due_date.isoformat(),
        "trace": [asdict(t) for t in r.trace],
    }
