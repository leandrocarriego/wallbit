"""Accountant actions on closes, plus the user side of alert conversations and notifications."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Header
from pydantic import BaseModel
from sqlalchemy import select

from app.core.errors import DomainError
from app.core.http import Actor, DbSession
from app.modules.alerts.engine import CloseStatus
from app.modules.classification.engine import Category
from app.modules.closing.models import CloseAlert, PeriodClose
from app.modules.demo.service import today
from app.modules.enrollment.service import get_client
from app.modules.notifications.models import Notification
from app.modules.review import service
from app.modules.review.models import AlertMessage, CloseSnapshot

router = APIRouter(tags=["accountant"])
user_router = APIRouter(prefix="/api/v1/clients", tags=["user"])


class CloseState(BaseModel):
    close_id: uuid.UUID
    status: CloseStatus
    version: int


class ResolveIn(BaseModel):
    resolution: str = "Resuelto por el contador"


class ClassifyIn(BaseModel):
    category: Category | None
    reason: str | None = None


class MessageIn(BaseModel):
    body: str


class MessageOut(BaseModel):
    id: uuid.UUID
    author: str
    body: str
    created_at: datetime


class ApproveIn(BaseModel):
    attested: bool


class SnapshotOut(BaseModel):
    snapshot_id: uuid.UUID
    close_id: uuid.UUID
    version: int
    approved_by: str
    approved_at: datetime
    message: str


class BatchIn(BaseModel):
    period: str
    include_info: bool = True
    attested: bool


class Conversation(BaseModel):
    alert_id: uuid.UUID
    close_id: uuid.UUID
    period: str
    title: str
    messages: list[MessageOut]


class NotificationOut(BaseModel):
    id: uuid.UUID
    period: str
    body: str
    status: str
    sent_at: datetime | None
    approved_by: str
    result: dict[str, Any]


def _state(close: PeriodClose) -> CloseState:
    return CloseState(close_id=close.id, status=close.status, version=close.version)


def _message_out(m: AlertMessage) -> MessageOut:
    return MessageOut(id=m.id, author=m.author, body=m.body, created_at=m.created_at)


P = "/api/v1/period-closes"


@router.post(P + "/{close_id}/alerts/{alert_id}/resolve")
def resolve(
    close_id: uuid.UUID, alert_id: uuid.UUID, body: ResolveIn, session: DbSession, actor: Actor
) -> CloseState:
    close = service.get_close(session, close_id)
    return _state(
        service.set_alert_status(
            session,
            close,
            alert_id,
            resolved=True,
            resolution=body.resolution,
            actor=actor,
            today=today(session),
        )
    )


@router.post(P + "/{close_id}/alerts/{alert_id}/reopen")
def reopen(
    close_id: uuid.UUID, alert_id: uuid.UUID, session: DbSession, actor: Actor
) -> CloseState:
    """Undo of a resolution."""
    close = service.get_close(session, close_id)
    return _state(
        service.set_alert_status(
            session,
            close,
            alert_id,
            resolved=False,
            resolution=None,
            actor=actor,
            today=today(session),
        )
    )


@router.post(P + "/{close_id}/movements/{movement_id}/classify")
def classify(
    close_id: uuid.UUID, movement_id: uuid.UUID, body: ClassifyIn, session: DbSession, actor: Actor
) -> CloseState:
    close = service.get_close(session, close_id)
    return _state(
        service.classify_movement(
            session,
            close,
            movement_id,
            category=body.category,
            reason=body.reason,
            actor=actor,
            today=today(session),
        )
    )


@router.get(P + "/{close_id}/alerts/{alert_id}/messages")
def list_messages(close_id: uuid.UUID, alert_id: uuid.UUID, session: DbSession) -> list[MessageOut]:
    service.get_alert(session, service.get_close(session, close_id), alert_id)
    return [_message_out(m) for m in service.messages(session, alert_id)]


@router.post(P + "/{close_id}/alerts/{alert_id}/messages")
def write_message(
    close_id: uuid.UUID, alert_id: uuid.UUID, body: MessageIn, session: DbSession, actor: Actor
) -> MessageOut:
    close = service.get_close(session, close_id)
    return _message_out(
        service.post_message(session, close, alert_id, author=actor, body=body.body)
    )


@router.post(P + "/{close_id}/approve")
def approve(close_id: uuid.UUID, body: ApproveIn, session: DbSession, actor: Actor) -> SnapshotOut:
    snapshot = service.approve(
        session, service.get_close(session, close_id), attested=body.attested, actor=actor
    )
    return SnapshotOut(
        snapshot_id=snapshot.id,
        close_id=snapshot.close_id,
        version=snapshot.version,
        approved_by=snapshot.approved_by,
        approved_at=snapshot.approved_at,
        message=snapshot.message,
    )


@router.post(P + "/batch-approve")
def batch_approve(
    body: BatchIn,
    session: DbSession,
    actor: Actor,
    idempotency_key: str | None = Header(default=None),
) -> dict[str, Any]:
    if not idempotency_key:
        raise DomainError("idempotency_key_required", "Falta el header Idempotency-Key.")
    return service.batch_approve(
        session,
        body.period,
        include_info=body.include_info,
        attested=body.attested,
        idempotency_key=idempotency_key,
        actor=actor,
    )


@user_router.get("/{client_id}/conversations")
def conversations(client_id: uuid.UUID, session: DbSession) -> list[Conversation]:
    client = get_client(session, client_id)
    result = []
    alert_ids = list(
        session.scalars(
            select(AlertMessage.alert_id).where(AlertMessage.client_id == client.id).distinct()
        )
    )
    for alert_id in alert_ids:
        alert = session.get(CloseAlert, alert_id)
        close = session.get(PeriodClose, alert.close_id) if alert else None
        if alert is None or close is None:
            continue
        result.append(
            Conversation(
                alert_id=alert.id,
                close_id=close.id,
                period=close.period,
                title=alert.title,
                messages=[_message_out(m) for m in service.messages(session, alert.id)],
            )
        )
    return result


@user_router.post("/{client_id}/alerts/{alert_id}/messages")
def reply(
    client_id: uuid.UUID, alert_id: uuid.UUID, body: MessageIn, session: DbSession, actor: Actor
) -> MessageOut:
    client = get_client(session, client_id)
    alert = session.get(CloseAlert, alert_id)
    close = session.get(PeriodClose, alert.close_id) if alert else None
    if close is None or close.client_id != client.id:
        raise DomainError("alert_not_found", "No existe esa conversación.")
    return _message_out(
        service.post_message(session, close, alert_id, author=actor, body=body.body)
    )


@user_router.get("/{client_id}/notifications")
def user_notifications(client_id: uuid.UUID, session: DbSession) -> list[NotificationOut]:
    client = get_client(session, client_id)
    out = []
    for n in session.scalars(
        select(Notification)
        .where(Notification.client_id == client.id)
        .order_by(Notification.created_at.desc())
    ):
        snapshot = session.get(CloseSnapshot, n.snapshot_id)
        assert snapshot is not None
        out.append(
            NotificationOut(
                id=n.id,
                period=snapshot.period,
                body=n.body,
                status=n.status.value,
                sent_at=n.sent_at,
                approved_by=snapshot.approved_by,
                result=snapshot.result,
            )
        )
    return out
