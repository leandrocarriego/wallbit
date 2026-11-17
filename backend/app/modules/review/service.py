"""Accountant actions on a close: resolve, classify, talk to the user, approve."""

import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.after_commit import enqueue_after_commit
from app.core.errors import DomainError, NotFoundError
from app.core.locks import lock_client
from app.modules.alerts.engine import CloseStatus, Severity
from app.modules.audit.service import record
from app.modules.classification.engine import Category
from app.modules.classification.models import MovementOverride
from app.modules.clients.models import Client
from app.modules.closing import service as closing
from app.modules.closing.models import AlertStatus, CloseAlert, PeriodClose
from app.modules.ingestion.models import Movement
from app.modules.notifications import service as notifications
from app.modules.notifications.models import Notification, NotificationStatus
from app.modules.review.models import AlertMessage, BatchApproval, CloseSnapshot

BATCH_CHUNK = 100


def get_close(session: Session, close_id: uuid.UUID) -> PeriodClose:
    close = session.get(PeriodClose, close_id)
    if close is None:
        raise NotFoundError("close_not_found", "No existe ese cierre.")
    return close


def get_alert(session: Session, close: PeriodClose, alert_id: uuid.UUID) -> CloseAlert:
    alert = session.get(CloseAlert, alert_id)
    if alert is None or alert.close_id != close.id:
        raise NotFoundError("alert_not_found", "No existe esa alerta en este cierre.")
    return alert


def _editable(close: PeriodClose) -> None:
    if close.status in closing.FROZEN:
        raise DomainError("close_frozen", "El cierre ya está aprobado: solo se reabre con motivo.")


def _recompute(session: Session, close: PeriodClose, today: date, actor: str) -> PeriodClose:
    return closing.compute_client_close(
        session, close.client_id, close.period, today=today, actor=actor
    )


def set_alert_status(
    session: Session,
    close: PeriodClose,
    alert_id: uuid.UUID,
    *,
    resolved: bool,
    resolution: str | None,
    actor: str,
    today: date,
) -> PeriodClose:
    """Resolve an alert (or undo it). Resolutions are kept across recomputes by alert key."""
    lock_client(session, close.client_id)
    _editable(close)
    alert = get_alert(session, close, alert_id)
    alert.status = AlertStatus.RESOLVED if resolved else AlertStatus.OPEN
    alert.resolved_by = actor if resolved else None
    alert.resolved_at = datetime.now(UTC) if resolved else None
    alert.resolution = resolution if resolved else None
    record(
        session,
        actor=actor,
        action="alert.resolved" if resolved else "alert.reopened",
        entity_type="close_alert",
        entity_id=alert.id,
        client_id=close.client_id,
        period=close.period,
        after={"key": alert.key, "resolution": resolution},
    )
    session.flush()
    return _recompute(session, close, today, actor)


def classify_movement(
    session: Session,
    close: PeriodClose,
    movement_id: uuid.UUID,
    *,
    category: Category | None,
    reason: str | None,
    actor: str,
    today: date,
) -> PeriodClose:
    """The accountant decides what a movement is. `category=None` undoes the decision."""
    lock_client(session, close.client_id)
    _editable(close)
    movement = session.get(Movement, movement_id)
    if movement is None or movement.client_id != close.client_id or movement.period != close.period:
        raise NotFoundError("movement_not_found", "Ese movimiento no es de este cierre.")
    override = session.scalars(
        select(MovementOverride).where(MovementOverride.movement_id == movement.id)
    ).first()
    if category is None:
        if override is not None:
            session.delete(override)
    else:
        override = override or MovementOverride(movement_id=movement.id)
        override.category = category
        override.reason = reason
        override.decided_by = actor
        override.decided_at = datetime.now(UTC)
        session.add(override)
    record(
        session,
        actor=actor,
        action="movement.classified_by_accountant" if category else "movement.override_removed",
        entity_type="movement",
        entity_id=movement.id,
        client_id=close.client_id,
        period=close.period,
        after={"category": category.value if category else None, "reason": reason},
    )
    session.flush()
    return _recompute(session, close, today, actor)


def post_message(
    session: Session, close: PeriodClose, alert_id: uuid.UUID, *, author: str, body: str
) -> AlertMessage:
    alert = get_alert(session, close, alert_id)
    if not body.strip():
        raise DomainError("empty_message", "El mensaje está vacío.")
    message = AlertMessage(
        alert_id=alert.id, client_id=close.client_id, author=author, body=body.strip()
    )
    session.add(message)
    record(
        session,
        actor=author,
        action="alert.message_posted",
        entity_type="close_alert",
        entity_id=alert.id,
        client_id=close.client_id,
        period=close.period,
        after={"key": alert.key},
    )
    session.flush()
    return message


def messages(session: Session, alert_id: uuid.UUID) -> list[AlertMessage]:
    return list(
        session.scalars(
            select(AlertMessage)
            .where(AlertMessage.alert_id == alert_id)
            .order_by(AlertMessage.created_at)
        )
    )


def record_view(session: Session, close: PeriodClose, *, actor: str) -> None:
    """Opening a close is the start of a review: approval minus the last view is review time."""
    record(
        session,
        actor=actor,
        action="close.viewed",
        entity_type="period_close",
        entity_id=close.id,
        client_id=close.client_id,
        period=close.period,
        after={"status": close.status.value, "version": close.version},
    )


def preview(session: Session, close: PeriodClose) -> dict[str, Any]:
    client = session.get(Client, close.client_id)
    assert client is not None
    template = notifications.active_template(session)
    if close.result is None:
        return {"message": "", "template_version": template.version}
    message = notifications.render_close_message(
        template, first_name=client.full_name.split()[0], period=close.period, result=close.result
    )
    return {"message": message, "template_version": template.version}


def approve(
    session: Session,
    close: PeriodClose,
    *,
    attested: bool,
    actor: str,
    batch_key: str | None = None,
) -> CloseSnapshot:
    """Freeze the close into an immutable snapshot and queue its notification."""
    if not attested:
        raise DomainError("attestation_required", "Falta la declaración del contador matriculado.")
    if close.status is not CloseStatus.READY:
        raise DomainError(
            "close_not_ready",
            "Solo se aprueba un cierre listo: quedan alertas bloqueantes o datos.",
        )
    if close.dirty:
        raise DomainError(
            "close_dirty", "El cierre se está recalculando: probá de nuevo en un momento."
        )
    client = session.get(Client, close.client_id)
    assert client is not None and close.result is not None
    template = notifications.active_template(session)
    alerts = [
        _alert_json(a)
        for a in session.scalars(
            select(CloseAlert).where(CloseAlert.close_id == close.id, CloseAlert.present.is_(True))
        )
    ]
    message = notifications.render_close_message(
        template, first_name=client.full_name.split()[0], period=close.period, result=close.result
    )
    now = datetime.now(UTC)
    snapshot = CloseSnapshot(
        close_id=close.id,
        client_id=client.id,
        period=close.period,
        version=close.version,
        inputs_hash=close.inputs_hash or "",
        engine_version=close.engine_version or "",
        params_name=close.params_name or "",
        result=close.result,
        alerts=alerts,
        message=message,
        template_version=template.version,
        approved_by=actor,
        approved_at=now,
        batch_key=batch_key,
    )
    session.add(snapshot)
    session.flush()
    notification = Notification(
        snapshot_id=snapshot.id,
        client_id=client.id,
        body=message,
        status=NotificationStatus.PENDING,
    )
    session.add(notification)
    close.status = CloseStatus.APPROVED
    session.flush()
    record(
        session,
        actor=actor,
        action="close.approved",
        entity_type="period_close",
        entity_id=close.id,
        client_id=client.id,
        period=close.period,
        after={
            "snapshot_id": str(snapshot.id),
            "version": snapshot.version,
            "inputs_hash": snapshot.inputs_hash,
            "batch_key": batch_key,
            "template_version": template.version,
        },
    )
    enqueue_after_commit(session, "notifications.send_close_notification", str(notification.id))
    return snapshot


def batch_approve(
    session: Session,
    period: str,
    *,
    include_info: bool,
    attested: bool,
    idempotency_key: str,
    actor: str,
) -> dict[str, Any]:
    """Approve every READY close of the period. Replaying the same key returns the first result."""
    done = session.scalars(
        select(BatchApproval).where(BatchApproval.idempotency_key == idempotency_key)
    ).first()
    if done is not None:
        return {**done.result, "replayed": True}
    if not attested:
        raise DomainError("attestation_required", "Falta la declaración del contador matriculado.")

    ready = list(
        session.scalars(
            select(PeriodClose)
            .where(PeriodClose.period == period, PeriodClose.status == CloseStatus.READY)
            .order_by(PeriodClose.id)
            .with_for_update(skip_locked=True)
        )
    )
    approved, skipped = [], []
    for start in range(0, len(ready), BATCH_CHUNK):
        for close in ready[start : start + BATCH_CHUNK]:
            if close.dirty or (not include_info and _has_info_alerts(session, close)):
                skipped.append(str(close.id))
                continue
            approve(session, close, attested=True, actor=actor, batch_key=idempotency_key)
            approved.append(str(close.id))
        session.flush()
    result = {
        "period": period,
        "approved": len(approved),
        "skipped": len(skipped),
        "replayed": False,
    }
    session.add(
        BatchApproval(
            idempotency_key=idempotency_key, period=period, approved_by=actor, result=result
        )
    )
    record(
        session,
        actor=actor,
        action="close.batch_approved",
        entity_type="period",
        period=period,
        after={**result, "idempotency_key": idempotency_key},
    )
    return result


def _has_info_alerts(session: Session, close: PeriodClose) -> bool:
    return (
        session.scalars(
            select(CloseAlert).where(
                CloseAlert.close_id == close.id,
                CloseAlert.present.is_(True),
                CloseAlert.severity == Severity.INFO,
            )
        ).first()
        is not None
    )


def _alert_json(a: CloseAlert) -> dict[str, Any]:
    return {
        "key": a.key,
        "type": a.type.value,
        "severity": a.severity.value,
        "title": a.title,
        "status": a.status.value,
        "resolved_by": a.resolved_by,
        "resolution": a.resolution,
    }


def mark_notified(session: Session, notification: Notification, *, actor: str) -> None:
    snapshot = session.get(CloseSnapshot, notification.snapshot_id)
    assert snapshot is not None
    close = session.get(PeriodClose, snapshot.close_id, with_for_update=True)
    if close is not None and close.status is CloseStatus.APPROVED:
        close.status = CloseStatus.NOTIFIED
        record(
            session,
            actor=actor,
            action="close.notified",
            entity_type="period_close",
            entity_id=close.id,
            client_id=close.client_id,
            period=close.period,
        )
