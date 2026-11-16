from datetime import date, datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps, UUIDPrimaryKey, str_enum
from app.core.enums import ActivityType, MonotributoCategory, TaxRegime


class Client(UUIDPrimaryKey, Timestamps, Base):
    """Wallbit user offered the accounting service, with their tax profile once enrolled."""

    __tablename__ = "clients"

    full_name: Mapped[str] = mapped_column(String(200))
    cuit: Mapped[str] = mapped_column(String(13), unique=True)
    activity: Mapped[str] = mapped_column(String(120))
    regime: Mapped[TaxRegime] = mapped_column(
        str_enum(TaxRegime, 20), default=TaxRegime.MONOTRIBUTO
    )
    # Unknown until ARCA is linked: the category is read from ARCA, never typed in.
    category: Mapped[MonotributoCategory | None] = mapped_column(str_enum(MonotributoCategory, 2))
    activity_type: Mapped[ActivityType] = mapped_column(
        str_enum(ActivityType, 20), default=ActivityType.SERVICES
    )
    jurisdiction: Mapped[str] = mapped_column(String(60))
    service_since: Mapped[date | None]

    # Enrollment: explicit, versioned consent, then a mandatory ARCA link.
    enrolled_at: Mapped[datetime | None]
    consent_version: Mapped[str | None] = mapped_column(String(20))
    arca_linked_at: Mapped[datetime | None]

    @property
    def is_active(self) -> bool:
        """Only enrolled clients with ARCA linked take part in the monthly close."""
        return self.enrolled_at is not None and self.arca_linked_at is not None
