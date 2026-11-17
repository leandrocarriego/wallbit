"""Accountant productivity: opening a close is audited and turns into review time."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.business_metrics import ACCOUNTANT_ACTIONS, ACTIONS_BY_ACTOR, REVIEW_SECONDS
from app.modules.audit.models import AuditEvent

from .test_review import ATTEST, P, make_martina_ready


def test_view_then_approve_measures_review_time(seeded: Session, api: TestClient) -> None:
    close = make_martina_ready(seeded, api)
    assert api.post(f"{P}/{close.id}/views").status_code == 204
    api.post(f"{P}/{close.id}/approve", json=ATTEST)

    views = seeded.scalars(select(AuditEvent).where(AuditEvent.action == "close.viewed")).all()
    assert [(v.actor, v.entity_id) for v in views] == [("accountant-demo", close.id)]
    period, n, avg, p50, _ = seeded.execute(REVIEW_SECONDS, {"max_seconds": 7200}).one()
    assert (period, n) == ("2026-10", 1) and 0 <= p50 == float(avg) < 60


def test_actions_count_the_accountant_and_not_the_users(seeded: Session, api: TestClient) -> None:
    close = make_martina_ready(seeded, api)
    api.post(f"{P}/{close.id}/views")
    seeded.flush()  # raw SQL does not autoflush pending ORM objects
    rows = seeded.execute(ACTIONS_BY_ACTOR, {"actions": ACCOUNTANT_ACTIONS}).all()
    actors = {actor for _, actor, _, _ in rows}
    actions = {action for _, _, action, _ in rows}
    assert actors == {"accountant-demo"}
    assert {"close.viewed", "alert.resolved", "movement.classified_by_accountant"} <= actions
