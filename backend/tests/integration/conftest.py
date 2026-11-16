"""Tests against a real Postgres (the compose one), in a separate database: `wallbit_test`.

If Postgres is not available, integration tests are skipped (e.g. pre-push without `make up`).
"""

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

from app.core.config import get_settings

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))


def _test_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _alembic_config(url: str) -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "migrations"))
    os.environ["DATABASE_URL"] = url
    get_settings.cache_clear()
    return cfg


@pytest.fixture(scope="session")
def db_url() -> Iterator[str]:
    url = _test_url()
    admin = create_engine(make_url(url).set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            name = make_url(url).database
            exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": name})
            if exists.scalar() is None:
                conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError:
        pytest.skip("Postgres no disponible: corré `make up` para los tests de integración")
    finally:
        admin.dispose()

    cfg = _alembic_config(url)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    yield url


@pytest.fixture(scope="session")
def engine(db_url: str) -> Iterator[Engine]:
    eng = create_engine(db_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """Each test runs inside a transaction that is rolled back at the end."""
    with engine.connect() as conn:
        trans = conn.begin()
        with Session(bind=conn, join_transaction_mode="create_savepoint") as s:
            yield s
        trans.rollback()


@pytest.fixture
def api(session: Session) -> Iterator["TestClient"]:
    """API client whose requests share the test's rolled-back transaction."""
    from fastapi.testclient import TestClient

    from app.core.http import db_session
    from app.main import app

    def override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[db_session] = override
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def seeded(session: Session) -> Session:
    from seeds import run

    run.seed_parameters(session)
    run.seed_rules(session)
    run.seed_martina(session)
    run.seed_mateo(session)
    from app.modules.demo.models import DemoClock

    session.add(DemoClock(id=1, today=run.DEMO_TODAY))
    session.flush()
    return session
