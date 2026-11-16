"""Request-scoped dependencies: DB session (one transaction per request) and actor."""

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.db import SessionLocal


def db_session() -> Iterator[Session]:
    """Commit when the request succeeds, roll back on any error."""
    with SessionLocal() as session, session.begin():
        yield session


def actor(x_actor: Annotated[str | None, Header()] = None) -> str:
    """No auth in the prototype (decision 10): the caller says who it is, and we audit it."""
    return x_actor or "accountant-demo"


DbSession = Annotated[Session, Depends(db_session)]
Actor = Annotated[str, Depends(actor)]
