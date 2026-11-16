from datetime import date

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey, str_enum
from app.core.enums import ActivityType, MonotributoCategory, TaxRegime


class Client(UUIDPrimaryKey, Timestamps, Base):
    """Wallbit user enrolled in the accounting service (tax profile)."""

    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(200))
    cuit: Mapped[str] = mapped_column(String(13), unique=True)
    activity: Mapped[str] = mapped_column(String(120))
    regime: Mapped[TaxRegime] = mapped_column(
        str_enum(TaxRegime, 20), default=TaxRegime.MONOTRIBUTO
    )
    category: Mapped[MonotributoCategory] = mapped_column(str_enum(MonotributoCategory, 2))
    activity_type: Mapped[ActivityType] = mapped_column(
        str_enum(ActivityType, 20), default=ActivityType.SERVICES
    )
    jurisdiction: Mapped[str] = mapped_column(String(60))
    service_since: Mapped[date]
