"""Notification templates (versioned, approved by the accountant) and in-app notifications."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey, str_enum


class NotificationTemplate(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "notification_templates"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_templates_name_version"),)

    name: Mapped[str] = mapped_column(String(60))
    version: Mapped[int]
    body: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(120))
    approved_at: Mapped[datetime]
    active: Mapped[bool] = mapped_column(default=True)


class NotificationStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"


class Notification(UUIDPrimaryKey, Timestamps, Base):
    """One per approved snapshot: re-sending is a no-op (idempotent effect)."""

    __tablename__ = "notifications"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("close_snapshots.id"), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[NotificationStatus] = mapped_column(str_enum(NotificationStatus, 20))
    sent_at: Mapped[datetime | None]
    read_at: Mapped[datetime | None]
