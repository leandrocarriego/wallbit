import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent


def record(
    session: Session,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    client_id: uuid.UUID | None = None,
    period: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    request_id: str | None = None,
    task_id: str | None = None,
) -> AuditEvent:
    """Add the event to the current transaction: it is saved with the change or not at all.

    Never commits on its own (ARCHITECTURE §5: audit in the same transaction).
    """
    event = AuditEvent(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        client_id=client_id,
        period=period,
        before=before,
        after=after,
        request_id=request_id,
        task_id=task_id,
    )
    session.add(event)
    return event
