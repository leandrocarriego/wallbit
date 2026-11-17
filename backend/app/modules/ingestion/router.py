"""Entry point for Wallbit movements.

In production this is a consumer of the core's movement events; in the prototype the same use
case is exposed over HTTP so the load tests can simulate many users getting paid at once.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.enums import Currency, Direction, MovementType
from app.core.http import Actor, DbSession
from app.modules.enrollment.router import _open_prompts
from app.modules.enrollment.schemas import PromptOut
from app.modules.enrollment.service import get_client
from app.modules.ingestion.service import IncomingMovement, ingest_movement

router = APIRouter(prefix="/api/v1/movements", tags=["ingestion"])


class MovementIn(BaseModel):
    client_id: uuid.UUID
    external_id: str = Field(max_length=64)
    occurred_at: datetime
    type: MovementType
    direction: Direction
    amount: Decimal = Field(gt=0)
    currency: Currency
    fx_rate_ars: Decimal = Field(gt=0)
    counterparty: str | None = Field(default=None, max_length=200)
    origin_country: str | None = Field(default=None, max_length=2)
    origin_provider: str | None = Field(default=None, max_length=80)
    origin_holder_name: str | None = Field(default=None, max_length=200)
    memo: str | None = Field(default=None, max_length=500)


class IngestOut(BaseModel):
    movement_id: uuid.UUID
    period: str
    created: bool
    prompts: list[PromptOut]  # the user's open prompts after classifying this movement


@router.post("")
def ingest(body: MovementIn, session: DbSession, actor: Actor) -> IngestOut:
    client = get_client(session, body.client_id)
    fields = body.model_dump(exclude={"client_id"})
    movement, created = ingest_movement(
        session, client, IncomingMovement(**fields), actor=actor, now=datetime.now(UTC)
    )
    return IngestOut(
        movement_id=movement.id,
        period=movement.period,
        created=created,
        prompts=_open_prompts(session, client),
    )
