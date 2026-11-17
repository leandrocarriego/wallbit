import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.enums import Currency, Direction, MovementType
from app.core.locks import lock_client
from app.core.periods import period_of
from app.modules.audit.service import record
from app.modules.classification.engine import normalize_name
from app.modules.classification.service import reclassify
from app.modules.clients.models import Client
from app.modules.closing.service import mark_dirty
from app.modules.ingestion.models import Counterparty, Movement


def counterparty_for(
    session: Session, raw_name: str | None, country: str | None = None
) -> Counterparty | None:
    """Return the single entity behind a raw name, creating it the first time we see it."""
    if not raw_name:
        return None
    key = normalize_name(raw_name)
    found = session.scalars(select(Counterparty).where(Counterparty.normalized_name == key)).first()
    if found is not None:
        # Prefer a properly cased name ("Acme Corp") over a shouted one ("ACME CORP").
        if found.display_name.isupper() and not raw_name.strip().isupper():
            found.display_name = raw_name.strip()
        return found
    created = Counterparty(normalized_name=key, display_name=raw_name.strip(), country=country)
    session.add(created)
    session.flush()
    return created


@dataclass(frozen=True)
class IncomingMovement:
    """A movement as Wallbit's core publishes it."""

    external_id: str
    occurred_at: datetime
    type: MovementType
    direction: Direction
    amount: Decimal
    currency: Currency
    fx_rate_ars: Decimal
    counterparty: str | None = None
    origin_country: str | None = None
    origin_provider: str | None = None
    origin_holder_name: str | None = None
    memo: str | None = None


def ingest_movement(
    session: Session, client: Client, data: IncomingMovement, *, actor: str, now: datetime
) -> tuple[Movement, bool]:
    """Store a movement and classify it right away (continuous classification).

    Idempotent by `external_id`: a redelivered event returns the stored movement untouched.
    """
    lock_client(session, client.id)
    existing = session.scalars(
        select(Movement).where(Movement.external_id == data.external_id)
    ).first()
    if existing is not None:
        return existing, False
    cp = counterparty_for(session, data.counterparty, data.origin_country)
    movement = Movement(
        id=uuid.uuid4(),
        client_id=client.id,
        external_id=data.external_id,
        occurred_at=data.occurred_at,
        period=period_of(data.occurred_at),
        type=data.type,
        direction=data.direction,
        amount=data.amount,
        currency=data.currency,
        fx_rate_ars=data.fx_rate_ars,
        counterparty_id=cp.id if cp else None,
        counterparty_raw=data.counterparty,
        origin_country=data.origin_country,
        origin_provider=data.origin_provider,
        origin_holder_name=data.origin_holder_name,
        memo=data.memo,
    )
    session.add(movement)
    session.flush()
    record(
        session,
        actor=actor,
        action="movement.ingested",
        entity_type="movement",
        entity_id=movement.id,
        client_id=client.id,
        period=movement.period,
        after={"type": data.type.value, "amount": str(data.amount)},
    )
    # Only clients with the service classify; the rest are classified when they link ARCA.
    if client.is_active:
        reclassify(session, client, movement.period, actor=actor, now=now)
        mark_dirty(session, client.id, movement.period)
    return movement, True
