from datetime import date

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.http import Actor, DbSession
from app.modules.demo import service

router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


class Clock(BaseModel):
    today: date


@router.get("/clock")
def get_clock(session: DbSession) -> Clock:
    return Clock(today=service.today(session))


@router.put("/clock")
def put_clock(body: Clock, session: DbSession, actor: Actor) -> Clock:
    return Clock(today=service.set_today(session, body.today, actor=actor))
