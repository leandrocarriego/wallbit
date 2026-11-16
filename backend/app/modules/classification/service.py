"""Glue between the DB and the pure classifier, plus the prompts it generates for the user."""

import uuid
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Direction, MovementType
from app.core.periods import first_day, local_date, shift
from app.modules.audit.service import record
from app.modules.classification import engine
from app.modules.classification.models import (
    CounterpartyDeclaration,
    GlobalRuleRow,
    MovementClassification,
)
from app.modules.clients.models import Client
from app.modules.ingestion.models import Counterparty, Movement
from app.modules.invoices.models import Invoice
from app.modules.prompts.models import PromptKind, PromptStatus, UserPrompt

HISTORY_MONTHS = 6


def rule_from_row(row: GlobalRuleRow) -> engine.GlobalRule:
    c = row.condition
    condition = engine.RuleCondition(
        movement_type=MovementType(c["movement_type"]) if c.get("movement_type") else None,
        counterparty_contains=tuple(c.get("counterparty_contains", ())),
        origin_provider_in=tuple(c.get("origin_provider_in", ())),
        holder_is_client=c.get("holder_is_client"),
    )
    return engine.GlobalRule(str(row.id), row.priority, condition, row.category, row.description)


def reclassify(
    session: Session, client: Client, period: str, *, actor: str, now: datetime
) -> list[MovementClassification]:
    """Classify every movement of the client in the period and refresh the user's prompts."""
    keys = _counterparty_keys(session)
    movements = list(
        session.scalars(
            select(Movement).where(Movement.client_id == client.id, Movement.period == period)
        )
    )
    ctx = _context(session, client, period, keys)
    results = engine.classify_period([_to_engine(m, keys) for m in movements], ctx)
    by_id = {str(m.id): m for m in movements}

    existing = {
        c.movement_id: c
        for c in session.scalars(
            select(MovementClassification).where(
                MovementClassification.client_id == client.id,
                MovementClassification.period == period,
            )
        )
    }
    stored: list[MovementClassification] = []
    for result in results:
        movement = by_id[result.movement_id]
        row = existing.get(movement.id) or MovementClassification(
            movement_id=movement.id, client_id=client.id, period=period
        )
        row.category = result.category
        row.source = result.source
        row.rule_id = uuid.UUID(result.rule_id) if result.rule_id else None
        row.invoice_id = uuid.UUID(result.invoice_id) if result.invoice_id else None
        row.declaration_id = uuid.UUID(result.declaration_id) if result.declaration_id else None
        row.suggestion = _suggestion_json(result.suggestion)
        row.trace = [asdict(step) for step in result.trace]
        row.classified_at = now
        session.add(row)
        stored.append(row)
    session.flush()

    if client.is_active:
        _sync_prompts(session, client, period, results, by_id, keys, now)
    record(
        session,
        actor=actor,
        action="classification.reclassified",
        entity_type="client",
        entity_id=client.id,
        client_id=client.id,
        period=period,
        after={
            "movements": len(results),
            "unclassified": sum(1 for r in results if r.needs_answer),
            "billable_without_invoice": sum(1 for r in results if r.billable and not r.invoice_id),
        },
    )
    return stored


def _counterparty_keys(session: Session) -> dict[uuid.UUID, tuple[str, str]]:
    return {
        cp.id: (cp.normalized_name, cp.display_name) for cp in session.scalars(select(Counterparty))
    }


def _to_engine(m: Movement, keys: dict[uuid.UUID, tuple[str, str]]) -> engine.MovementIn:
    key, display = keys.get(m.counterparty_id, (None, None)) if m.counterparty_id else (None, None)
    return engine.MovementIn(
        id=str(m.id),
        type=m.type,
        direction=m.direction,
        amount=m.amount,
        currency=m.currency,
        occurred_on=local_date(m.occurred_at),
        counterparty_key=key,
        counterparty_name=display or m.counterparty_raw,
        origin_holder_name=m.origin_holder_name,
        origin_provider=m.origin_provider,
        origin_country=m.origin_country,
        memo=m.memo,
    )


def _context(
    session: Session, client: Client, period: str, keys: dict[uuid.UUID, tuple[str, str]]
) -> engine.ClassificationContext:
    def key_of(cp_id: uuid.UUID | None) -> str | None:
        return keys[cp_id][0] if cp_id in keys else None

    rules = [
        rule_from_row(r) for r in session.scalars(select(GlobalRuleRow).where(GlobalRuleRow.active))
    ]

    # Invoices that could pay this period's movements, minus those already used by other periods.
    window_start = first_day(period) - timedelta(days=45)
    window_end = first_day(shift(period, 1)) + timedelta(days=15)
    used_elsewhere = set(
        session.scalars(
            select(MovementClassification.invoice_id).where(
                MovementClassification.client_id == client.id,
                MovementClassification.period != period,
                MovementClassification.invoice_id.is_not(None),
            )
        )
    )
    all_invoices = list(session.scalars(select(Invoice).where(Invoice.client_id == client.id)))
    candidates = [
        engine.InvoiceIn(
            str(i.id),
            i.number,
            key_of(i.counterparty_id),
            i.amount,
            i.currency,
            i.issued_on,
            for_movement_id=str(i.issued_for_movement_id) if i.issued_for_movement_id else None,
        )
        for i in all_invoices
        if window_start <= i.issued_on <= window_end and i.id not in used_elsewhere
    ]
    invoiced = frozenset(k for i in all_invoices if (k := key_of(i.counterparty_id)))

    declarations = [
        engine.Declaration(str(d.id), keys[d.counterparty_id][0], d.category)
        for d in session.scalars(
            select(CounterpartyDeclaration).where(CounterpartyDeclaration.client_id == client.id)
        )
    ]

    history_from = shift(period, -HISTORY_MONTHS)
    history = [
        engine.PriorPayment(key, m.period, m.amount)
        for m in session.scalars(
            select(Movement).where(
                Movement.client_id == client.id,
                Movement.direction == Direction.IN,
                Movement.period >= history_from,
                Movement.period < period,
            )
        )
        if (key := key_of(m.counterparty_id))
    ]
    return engine.ClassificationContext(
        client_full_name=client.full_name,
        rules=rules,
        invoices=candidates,
        declarations=declarations,
        history=history,
        invoiced_counterparties=invoiced,
    )


def _suggestion_json(s: engine.Suggestion | None) -> dict[str, Any] | None:
    if s is None:
        return None
    return {"category": s.category.value, "score": s.score, "reasons": list(s.reasons)}


def _sync_prompts(
    session: Session,
    client: Client,
    period: str,
    results: list[engine.Classification],
    movements: dict[str, Movement],
    keys: dict[uuid.UUID, tuple[str, str]],
    now: datetime,
) -> None:
    """Open the prompts the user needs now and resolve the ones that no longer apply."""
    wanted: dict[tuple[uuid.UUID, PromptKind], dict[str, Any]] = {}
    for r in results:
        m = movements[r.movement_id]
        base = {
            "counterparty": keys[m.counterparty_id][1]
            if m.counterparty_id in keys
            else m.counterparty_raw,
            "amount": str(m.amount),
            "currency": m.currency.value,
            "date": local_date(m.occurred_at).isoformat(),
        }
        if r.needs_answer:
            wanted[(m.id, PromptKind.WHO_IS)] = {
                **base,
                "suggestion": _suggestion_json(r.suggestion),
            }
        if r.billable and r.invoice_id is None:
            wanted[(m.id, PromptKind.INVOICE_THIS)] = {**base, "fx_rate_ars": str(m.fx_rate_ars)}

    prompts = list(
        session.scalars(
            select(UserPrompt).where(UserPrompt.client_id == client.id, UserPrompt.period == period)
        )
    )
    for p in prompts:
        if p.status is PromptStatus.OPEN and (p.movement_id, p.kind) not in wanted:
            p.status = PromptStatus.RESOLVED
            p.closed_at = now
    # Never reopen a prompt that already expired to the accountant.
    taken = {
        (p.movement_id, p.kind)
        for p in prompts
        if p.status in (PromptStatus.OPEN, PromptStatus.EXPIRED)
    }
    for (movement_id, kind), payload in wanted.items():
        if (movement_id, kind) not in taken:
            session.add(
                UserPrompt(
                    client_id=client.id,
                    movement_id=movement_id,
                    period=period,
                    kind=kind,
                    status=PromptStatus.OPEN,
                    payload=payload,
                )
            )
    session.flush()
