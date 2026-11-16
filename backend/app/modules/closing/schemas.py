import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.core.enums import Currency, MonotributoCategory
from app.modules.alerts.engine import AlertType, CloseStatus, Severity
from app.modules.classification.engine import Category, Source
from app.modules.closing.models import AlertStatus


class AlertOut(BaseModel):
    id: uuid.UUID
    key: str
    type: AlertType
    severity: Severity
    title: str
    detail: str
    subject_id: uuid.UUID | None
    amount: Decimal | None
    status: AlertStatus


class InboxRow(BaseModel):
    close_id: uuid.UUID
    client_id: uuid.UUID
    full_name: str
    cuit: str
    category: MonotributoCategory | None
    status: CloseStatus
    invoiced_usd: Decimal | None
    collected_usd: Decimal | None
    cap_usage_pct: Decimal | None
    alerts: list[AlertOut]


class Inbox(BaseModel):
    period: str
    started: bool
    today: date
    counts: dict[CloseStatus, int]
    total: int
    filtered_total: int
    blocking_alerts: int
    limit: int
    offset: int
    rows: list[InboxRow]


class MovementOut(BaseModel):
    id: uuid.UUID
    occurred_on: date
    type: str
    direction: str
    amount: Decimal
    currency: Currency
    counterparty: str | None
    memo: str | None
    category: Category | None
    source: Source | None
    invoice_number: str | None
    suggestion: dict[str, Any] | None
    trace: list[dict[str, str]]


class InvoiceRow(BaseModel):
    id: uuid.UUID
    number: str
    issued_on: date
    customer_name: str
    amount: Decimal
    currency: Currency
    fx_rate_ars: Decimal
    source: str
    received_at: datetime


class AuditRow(BaseModel):
    created_at: datetime
    actor: str
    action: str
    after: dict[str, Any] | None


class CloseDetail(BaseModel):
    close_id: uuid.UUID
    period: str
    status: CloseStatus
    version: int
    computed_at: datetime | None
    engine_version: str | None
    params_name: str | None
    client: dict[str, Any]
    result: dict[str, Any] | None
    alerts: list[AlertOut]
    movements: list[MovementOut]
    invoices: list[InvoiceRow]
    history: list[AuditRow]


class DayOut(BaseModel):
    today: date
    period: str
