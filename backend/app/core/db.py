import uuid
from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import DateTime, Enum, MetaData, Numeric, String, create_engine, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import get_settings

# Per-process pool (see ARCHITECTURE §5): bounded and predictable. PgBouncer is for production.
engine = create_engine(
    get_settings().database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

# Stable constraint names so Alembic generates reproducible migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Money types (CONVENTIONS): amounts NUMERIC(18,2), exchange rates NUMERIC(18,6).
Money = Numeric(18, 2)
FxRate = Numeric(18, 6)
PERIOD_CHECK = "~ '^[0-9]{4}-(0[1-9]|1[0-2])$'"


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        Decimal: Money,
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB,
        list[dict[str, str]]: JSONB,
        list[dict[str, Any]]: JSONB,
    }


class UUIDPrimaryKey:
    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


def str_enum(enum_cls: type[StrEnum], length: int = 30) -> Enum:
    """Enum stored as VARCHAR by *value* (not name), with a CHECK of allowed values."""
    return Enum(
        enum_cls,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


def period_column() -> Mapped[str]:
    """Accounting period `YYYY-MM` (Argentina time), validated by a per-table CHECK."""
    return mapped_column(String(7), index=True)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def ping_db() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
