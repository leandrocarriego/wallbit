"""Enqueue Celery tasks only after the DB transaction commits (ARCHITECTURE §5).

Enqueuing before the commit lets a worker read stale data; enqueuing outside the transaction
can lose the message if the process dies right after committing. Pending tasks live in
`session.info` and are sent from an `after_commit` hook; a periodic sweep recovers the rest.
"""

from typing import Any

from sqlalchemy import event
from sqlalchemy.orm import Session

_KEY = "after_commit_tasks"


def enqueue_after_commit(session: Session, task_name: str, *args: Any) -> None:
    session.info.setdefault(_KEY, []).append((task_name, args))


@event.listens_for(Session, "after_commit")
def _send_pending(session: Session) -> None:
    pending = session.info.pop(_KEY, [])
    if not pending:
        return
    from app.worker import celery_app

    for task_name, args in pending:
        celery_app.send_task(task_name, args=list(args))


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(_KEY, None)
