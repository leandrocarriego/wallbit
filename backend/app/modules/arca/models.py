"""Mock ARCA: a fictitious tax authority living in our DB, for the prototype only.

In the proposal these tables disappear and AfipSDK takes their place behind the same ports
(ARCHITECTURE §10). Nothing here is ever sent outside the system.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, FxRate, Timestamps, UUIDPrimaryKey, str_enum
from app.core.enums import ActivityType, Currency, MonotributoCategory


class ArcaRegistration(UUIDPrimaryKey, Timestamps, Base):
    """Taxpayer record as ARCA knows it (regime and category)."""

    __tablename__ = "arca_registrations"

    cuit: Mapped[str] = mapped_column(String(13), unique=True)
    category: Mapped[MonotributoCategory] = mapped_column(str_enum(MonotributoCategory, 2))
    activity_type: Mapped[ActivityType] = mapped_column(str_enum(ActivityType, 20))


class ArcaDocument(UUIDPrimaryKey, Timestamps, Base):
    """An invoice issued in ARCA by a taxpayer."""

    __tablename__ = "arca_documents"
    __table_args__ = (UniqueConstraint("cuit", "number", name="uq_arca_documents_cuit_number"),)

    cuit: Mapped[str] = mapped_column(String(13), index=True)
    number: Mapped[str] = mapped_column(String(20))
    issued_on: Mapped[date]
    customer_name: Mapped[str] = mapped_column(String(200))
    customer_country: Mapped[str | None] = mapped_column(String(2))
    description: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal]
    currency: Mapped[Currency] = mapped_column(str_enum(Currency, 4))
    fx_rate_ars: Mapped[Decimal] = mapped_column(FxRate)
    issued_via_wallbit: Mapped[bool] = mapped_column(default=False)
