from datetime import date

from sqlalchemy.orm import Session

from app.modules.audit.service import record
from app.modules.demo.models import DemoClock

DEFAULT_TODAY = date(2026, 10, 31)


def today(session: Session) -> date:
    clock = session.get(DemoClock, 1)
    return clock.today if clock else DEFAULT_TODAY


def set_today(session: Session, value: date, *, actor: str) -> date:
    clock = session.get(DemoClock, 1) or DemoClock(id=1, today=value)
    before = clock.today
    clock.today = value
    session.add(clock)
    record(
        session,
        actor=actor,
        action="demo.clock_set",
        entity_type="demo_clock",
        before={"today": before.isoformat()},
        after={"today": value.isoformat()},
    )
    return value
