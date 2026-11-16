"""Wallbit movements (read-only for the accounting service) and normalized counterparties."""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import (
    PERIOD_CHECK,
    Base,
    FxRate,
    Timestamps,
    UUIDPrimaryKey,
    period_column,
    str_enum,
)
from app.core.enums import Currency, Direction, MovementType

__all__ = ["Counterparty", "Direction", "Movement", "MovementType"]


class Counterparty(UUIDPrimaryKey, Timestamps, Base):
    """Single entity behind incoming names ("ACME CORP" = "Acme Corp.")."""

    __tablename__ = "counterparties"

    normalized_name: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(2))


class Movement(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "movements"
    __table_args__ = (
        CheckConstraint(f"period {PERIOD_CHECK}", name="period_format"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_movements_client_period", "client_id", "period"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id")
    )  # covered by the composite index
    external_id: Mapped[str] = mapped_column(
        String(64), unique=True
    )  # Wallbit id: idempotent ingestion
    occurred_at: Mapped[datetime]
    period: Mapped[str] = period_column()
    type: Mapped[MovementType] = mapped_column(str_enum(MovementType, 30))
    direction: Mapped[Direction] = mapped_column(str_enum(Direction, 3))
    amount: Mapped[Decimal]
    currency: Mapped[Currency] = mapped_column(str_enum(Currency, 4))
    fx_rate_ars: Mapped[Decimal] = mapped_column(FxRate)  # ARS per unit at transaction time
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), index=True
    )
    counterparty_raw: Mapped[str | None] = mapped_column(String(200))
    origin_holder_name: Mapped[str | None] = mapped_column(String(200))
    origin_provider: Mapped[str | None] = mapped_column(String(80))  # payoneer, paypal, bank, ...
    origin_country: Mapped[str | None] = mapped_column(String(2))
    memo: Mapped[str | None] = mapped_column(String(500))
