"""Things we ask the user while the month is running (decision 20)."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey, period_column, str_enum


class PromptKind(StrEnum):
    WHO_IS = "who_is"  # "¿Quién es J. Pérez?"
    INVOICE_THIS = "invoice_this"  # "Facturar este cobro"


class PromptStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"  # the user acted (declared or invoiced)
    RESOLVED = "resolved"  # no longer needed (e.g. an invoice showed up in ARCA)
    EXPIRED = "expired"  # unanswered by day 5: goes to the accountant


class UserPrompt(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "user_prompts"
    __table_args__ = (
        # At most one open prompt of each kind per movement.
        Index(
            "uq_user_prompts_open",
            "movement_id",
            "kind",
            unique=True,
            postgresql_where=text("status = 'open'"),
        ),
        Index("ix_user_prompts_client_status", "client_id", "status"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    movement_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("movements.id"))
    period: Mapped[str] = period_column()
    kind: Mapped[PromptKind] = mapped_column(str_enum(PromptKind, 20))
    status: Mapped[PromptStatus] = mapped_column(str_enum(PromptStatus, 20))
    payload: Mapped[dict[str, Any]]  # what the UI shows: counterparty, amount, suggestion…
    closed_at: Mapped[datetime | None]
