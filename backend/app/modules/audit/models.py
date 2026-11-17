"""Append-only audit log, partitioned by month (ARCHITECTURE §5.1).

Partitions and the trigger that rejects UPDATE/DELETE are created in the migration.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Index, PrimaryKeyConstraint, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        PrimaryKeyConstraint(
            "id", "created_at", name="pk_audit_events"
        ),  # includes the partition key
        Index("ix_audit_events_action_period_entity", "action", "period", "entity_id"),
        {"postgresql_partition_by": "RANGE (created_at)"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    actor: Mapped[str] = mapped_column(String(120))  # accountant-demo, client:<id>, system
    action: Mapped[str] = mapped_column(String(80))  # invoice.confirmed, close.approved, ...
    entity_type: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[uuid.UUID | None]
    client_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    period: Mapped[str | None] = mapped_column(String(7))
    request_id: Mapped[str | None] = mapped_column(String(64))
    task_id: Mapped[str | None] = mapped_column(String(64))
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
