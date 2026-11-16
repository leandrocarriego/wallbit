"""Demo clock: the simulated "today" that drives the close calendar in the prototype."""

from datetime import date

from sqlalchemy import CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, Timestamps


class DemoClock(Timestamps, Base):
    __tablename__ = "demo_clock"
    __table_args__ = (CheckConstraint("id = 1", name="single_row"),)

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    today: Mapped[date]
