from collections.abc import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# Pool por proceso (ver ARCHITECTURE §5): acotado y predecible. PgBouncer queda para producción.
engine = create_engine(
    get_settings().database_url,
    pool_size=5,
    max_overflow=5,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


def ping_db() -> bool:
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return True
