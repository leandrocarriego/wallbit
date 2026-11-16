"""Persistence for the classifier: global rules, user declarations and current classifications."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey, period_column, str_enum
from app.modules.classification.engine import Category, Source


class GlobalRuleRow(UUIDPrimaryKey, Timestamps, Base):
    """Global rule maintained by the accountant. There are no per-client rules (decision 14)."""

    __tablename__ = "global_rules"

    priority: Mapped[int]
    description: Mapped[str] = mapped_column(String(200))
    condition: Mapped[dict[str, Any]]  # serialized RuleCondition
    category: Mapped[Category] = mapped_column(str_enum(Category, 30))
    active: Mapped[bool] = mapped_column(default=True)
    created_by: Mapped[str] = mapped_column(String(120))


class CounterpartyDeclaration(UUIDPrimaryKey, Timestamps, Base):
    """What a client says a counterparty is. Evidence for the accountant, not a final decision."""

    __tablename__ = "counterparty_declarations"
    __table_args__ = (
        UniqueConstraint("client_id", "counterparty_id", name="uq_declarations_client_cp"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    counterparty_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("counterparties.id"))
    category: Mapped[Category] = mapped_column(str_enum(Category, 30))
    declared_by: Mapped[str] = mapped_column(String(120))
    declared_at: Mapped[datetime]


class MovementClassification(UUIDPrimaryKey, Timestamps, Base):
    """Current classification of a movement; rewritten on every reclassification."""

    __tablename__ = "movement_classifications"
    __table_args__ = (Index("ix_movement_classifications_client_period", "client_id", "period"),)

    movement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movements.id"), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    period: Mapped[str] = period_column()
    category: Mapped[Category] = mapped_column(str_enum(Category, 30))
    source: Mapped[Source] = mapped_column(str_enum(Source, 20))
    rule_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("global_rules.id"))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    declaration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparty_declarations.id")
    )
    suggestion: Mapped[dict[str, Any] | None]
    trace: Mapped[list[dict[str, str]]]
    classified_at: Mapped[datetime]
