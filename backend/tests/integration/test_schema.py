import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import Currency, Direction, MonotributoCategory, MovementType
from app.modules.audit.service import record
from app.modules.clients.models import Client
from app.modules.ingestion.models import Movement

from .conftest import _alembic_config


def _client(session: Session) -> Client:
    client = Client(
        full_name="Martina Ríos",
        cuit="27-30000012-4",
        activity="Diseño UX",
        category=MonotributoCategory.D,
        jurisdiction="CABA",
        service_since=date(2026, 3, 1),
    )
    session.add(client)
    session.flush()
    return client


def _movement(client: Client, **overrides: object) -> Movement:
    data: dict[str, object] = {
        "client_id": client.id,
        "external_id": f"wb-{uuid.uuid4()}",
        "occurred_at": datetime(2026, 10, 12, 15, 0, tzinfo=UTC),
        "period": "2026-10",
        "type": MovementType.INCOMING_TRANSFER,
        "direction": Direction.IN,
        "amount": Decimal("1200.00"),
        "currency": Currency.USD,
        "fx_rate_ars": Decimal("1450.000000"),
        "counterparty_raw": "ACME CORP",
    }
    data.update(overrides)
    return Movement(**data)


def test_migrations_upgrade_and_downgrade_cleanly_when_run_twice(db_url: str) -> None:
    cfg = _alembic_config(db_url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


def test_money_roundtrips_exactly_when_stored_as_numeric(session: Session) -> None:
    client = _client(session)
    session.add(_movement(client, amount=Decimal("0.10"), fx_rate_ars=Decimal("1450.123456")))
    session.flush()
    stored = session.scalars(select(Movement).where(Movement.client_id == client.id)).one()
    assert stored.amount == Decimal("0.10")
    assert stored.fx_rate_ars == Decimal("1450.123456")


def test_enums_are_stored_by_value_when_persisted(session: Session) -> None:
    client = _client(session)
    session.add(_movement(client))
    session.flush()
    raw = session.execute(
        text("SELECT type, direction FROM movements WHERE client_id = :c"), {"c": client.id}
    ).one()
    assert tuple(raw) == ("incoming_transfer", "in")


def test_movement_is_rejected_when_period_is_malformed(session: Session) -> None:
    client = _client(session)
    session.add(_movement(client, period="2026-13"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_movement_is_rejected_when_enum_value_is_unknown(session: Session) -> None:
    client = _client(session)
    with pytest.raises(IntegrityError):
        session.execute(
            text(
                "INSERT INTO movements (client_id, external_id, occurred_at, period, type,"
                " direction, amount, currency, fx_rate_ars) VALUES (:c, 'x', now(), '2026-10',"
                " 'gift', 'in', 1, 'USD', 1)"
            ),
            {"c": client.id},
        )


def test_audit_event_lands_in_its_monthly_partition_when_recorded(session: Session) -> None:
    event = record(session, actor="system", action="close.computed", entity_type="period_close")
    event.created_at = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
    session.flush()
    partition = session.execute(
        text("SELECT tableoid::regclass::text FROM audit_events WHERE id = :i"), {"i": event.id}
    ).scalar_one()
    assert partition == "audit_events_2026_11"


@pytest.mark.parametrize(
    "statement", ["UPDATE audit_events SET actor = 'x'", "DELETE FROM audit_events"]
)
def test_audit_events_reject_changes_when_already_written(session: Session, statement: str) -> None:
    record(session, actor="accountant-demo", action="close.approved", entity_type="period_close")
    session.flush()
    with pytest.raises(DBAPIError, match="append-only"):
        session.execute(text(statement))
