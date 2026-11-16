"""Versioned tax parameters with validity ranges. Loaded by the accountant, never hardcoded."""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, Timestamps, UUIDPrimaryKey, str_enum
from app.core.enums import MonotributoCategory


class TaxParameterSet(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tax_parameter_sets"
    __table_args__ = (
        CheckConstraint("valid_to IS NULL OR valid_to > valid_from", name="valid_range"),
    )

    name: Mapped[str] = mapped_column(String(60), unique=True)
    valid_from: Mapped[date]
    valid_to: Mapped[date | None]
    regime_max_annual_ars: Mapped[Decimal]
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(120))

    categories: Mapped[list["MonotributoCategoryParam"]] = relationship(
        back_populates="parameter_set", order_by="MonotributoCategoryParam.category"
    )


class MonotributoCategoryParam(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "monotributo_categories"
    __table_args__ = (
        UniqueConstraint("parameter_set_id", "category", name="uq_monotributo_categories_set_cat"),
        CheckConstraint("annual_cap_ars > 0", name="cap_positive"),
    )

    parameter_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tax_parameter_sets.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[MonotributoCategory] = mapped_column(str_enum(MonotributoCategory, 2))
    annual_cap_ars: Mapped[Decimal]
    monthly_fee_services_ars: Mapped[Decimal]
    monthly_fee_goods_ars: Mapped[Decimal]

    parameter_set: Mapped[TaxParameterSet] = relationship(back_populates="categories")
