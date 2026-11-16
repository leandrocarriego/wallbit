"""Accountant review: conversations on alerts, immutable snapshots and batch approvals."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey, period_column


class AlertMessage(UUIDPrimaryKey, Timestamps, Base):
    """A message in the conversation attached to one alert (replaces WhatsApp)."""

    __tablename__ = "alert_messages"

    alert_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("close_alerts.id"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    author: Mapped[str] = mapped_column(String(120))  # accountant-demo | client:<id>
    body: Mapped[str] = mapped_column(Text)


class CloseSnapshot(UUIDPrimaryKey, Timestamps, Base):
    """Frozen copy of an approved close. Append-only (trigger in the migration)."""

    __tablename__ = "close_snapshots"
    __table_args__ = (
        UniqueConstraint("close_id", "version", name="uq_close_snapshots_close_version"),
    )

    close_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("period_closes.id"), index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    period: Mapped[str] = period_column()
    version: Mapped[int]
    inputs_hash: Mapped[str] = mapped_column(String(64))
    engine_version: Mapped[str] = mapped_column(String(20))
    params_name: Mapped[str] = mapped_column(String(60))
    result: Mapped[dict[str, Any]]
    alerts: Mapped[list[dict[str, Any]]]
    message: Mapped[str] = mapped_column(Text)
    template_version: Mapped[int]
    approved_by: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime]
    batch_key: Mapped[str | None] = mapped_column(String(80))


class BatchApproval(UUIDPrimaryKey, Timestamps, Base):
    """Idempotency record for batch approvals: the same key never approves twice."""

    __tablename__ = "batch_approvals"

    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    period: Mapped[str] = period_column()
    approved_by: Mapped[str] = mapped_column(String(120))
    result: Mapped[dict[str, Any]]
