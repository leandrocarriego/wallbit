"""Per-client serialization of writes.

Two requests for the same client at once (a payment arriving while the user answers, or the
worker recomputing) used to race: both classified the same movements and one failed on the
unique key (found by k6 `user_activity`). Every write use case takes its client's lock first,
before touching any row, so lock order is always client → rows and they cannot deadlock.
It is a transaction-level advisory lock: released on commit or rollback, nothing to clean up.
"""

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session


def lock_client(session: Session, client_id: uuid.UUID) -> None:
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"client:{client_id}"},
    )
