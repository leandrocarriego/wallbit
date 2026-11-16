"""Type E invoices (export of services) for each client, always sourced from ARCA."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
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
from app.core.enums import Currency


class InvoiceSource(StrEnum):
    ARCA_IMPORTED = "arca_imported"  # read from ARCA (issued elsewhere)
    ARCA_ISSUED = "arca_issued"  # issued from Wallbit ("Facturar este cobro")


class Invoice(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("client_id", "number", name="uq_invoices_client_number"),
        CheckConstraint(f"period {PERIOD_CHECK}", name="period_format"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"), index=True)
    arca_document_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("arca_documents.id"), unique=True
    )
    number: Mapped[str] = mapped_column(String(20))  # "E 0001-00000043"
    issued_on: Mapped[date]
    period: Mapped[str] = period_column()
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("counterparties.id"))
    customer_name: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal]
    currency: Mapped[Currency] = mapped_column(str_enum(Currency, 4))
    fx_rate_ars: Mapped[Decimal] = mapped_column(FxRate)  # rate stated on the invoice
    source: Mapped[InvoiceSource] = mapped_column(str_enum(InvoiceSource, 30))
    received_at: Mapped[datetime]
    # Payment this invoice was issued for from Wallbit, if any (explicit match).
    issued_for_movement_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movements.id"))
