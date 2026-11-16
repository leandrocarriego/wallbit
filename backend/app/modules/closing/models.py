"""Monthly close per client and period, and its alerts."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import PERIOD_CHECK, Base, Timestamps, UUIDPrimaryKey, period_column, str_enum
from app.modules.alerts.engine import AlertType, CloseStatus, Severity


class PeriodClose(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "period_closes"
    __table_args__ = (
        UniqueConstraint("client_id", "period", name="uq_period_closes_client_period"),
        CheckConstraint(f"period {PERIOD_CHECK}", name="period_format"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    period: Mapped[str] = period_column()
    status: Mapped[CloseStatus] = mapped_column(str_enum(CloseStatus, 20))
    # Set by anything that changes the inputs; the sweep recomputes dirty closes.
    dirty: Mapped[bool] = mapped_column(default=True)
    inputs_hash: Mapped[str | None] = mapped_column(String(64))
    result: Mapped[dict[str, Any] | None]
    engine_version: Mapped[str | None] = mapped_column(String(20))
    params_name: Mapped[str | None] = mapped_column(String(60))
    computed_at: Mapped[datetime | None]
    version: Mapped[int] = mapped_column(default=0)  # bumps on every effective recompute


class AlertStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class CloseAlert(UUIDPrimaryKey, Timestamps, Base):
    """Alert of a close. Its `key` is stable, so a resolution survives recomputes."""

    __tablename__ = "close_alerts"
    __table_args__ = (UniqueConstraint("close_id", "key", name="uq_close_alerts_close_key"),)

    close_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("period_closes.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(120))
    type: Mapped[AlertType] = mapped_column(str_enum(AlertType, 30))
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, 20))
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(String(400))
    subject_id: Mapped[uuid.UUID | None]
    amount: Mapped[Decimal | None]
    status: Mapped[AlertStatus] = mapped_column(str_enum(AlertStatus, 20))
    present: Mapped[bool] = mapped_column(default=True)  # false once the last compute drops it
    resolved_by: Mapped[str | None] = mapped_column(String(120))
    resolved_at: Mapped[datetime | None]
    resolution: Mapped[str | None] = mapped_column(String(200))
