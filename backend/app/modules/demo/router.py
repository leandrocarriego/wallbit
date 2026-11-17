from datetime import date

from fastapi import APIRouter, status
from pydantic import BaseModel

from app.core.http import Actor, DbSession
from app.core.periods import first_day, period_of, shift
from app.modules.audit.service import record
from app.modules.closing import service as closing
from app.modules.closing.schemas import DayOut
from app.modules.demo import service
from seeds import run as demo_seed

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class Clock(BaseModel):
    today: date


@router.get("/clock")
def get_clock(session: DbSession) -> Clock:
    return Clock(today=service.today(session))


@router.put("/clock")
def put_clock(body: Clock, session: DbSession, actor: Actor) -> Clock:
    return Clock(today=service.set_today(session, body.today, actor=actor))


@router.post("/day-1")
def simulate_day_1(session: DbSession, actor: Actor) -> DayOut:
    """Same as Beat on day 1 at 00:05: move the clock and start the close of last month."""
    current = service.today(session)
    # Pressing it again after day 1 restarts the same close instead of jumping a month.
    period = closing.previous_period(current) if current.day <= 20 else period_of(current)
    new_today = first_day(shift(period, 1))
    service.set_today(session, new_today, actor=actor)
    closing.start_period_close(session, period, actor=actor)
    return DayOut(today=new_today, period=period)


@router.post("/day-5")
def simulate_day_5(session: DbSession, actor: Actor) -> DayOut:
    """Same as Beat after day 5: unanswered questions expire and go to the accountant."""
    period = closing.previous_period(service.today(session))
    new_today = first_day(shift(period, 1)).replace(day=closing.ANSWER_DEADLINE_DAY + 1)
    service.set_today(session, new_today, actor=actor)
    closing.expire_pending_questions(session, period, actor=actor)
    return DayOut(today=new_today, period=period)


@router.post("/reset", status_code=status.HTTP_204_NO_CONTENT)
def reset_demo(session: DbSession, actor: Actor) -> None:
    """Same as `make seed`: wipe all data and reload the demo, to run the walkthrough again."""
    demo_seed.seed_demo(session)
    record(session, actor=actor, action="demo.reset", entity_type="demo_clock")
