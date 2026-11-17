"""Day-1 consolidation, recompute after user actions and the day-5 deadline."""

import uuid
from datetime import date

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.alerts.engine import AlertType, CloseStatus, Severity
from app.modules.closing import service
from app.modules.closing.models import CloseAlert, PeriodClose
from app.modules.prompts.models import PromptKind, PromptStatus, UserPrompt

from .test_user_flow import ACTOR, client_id, onboard

PERIOD = "2026-10"
DAY_1 = date(2026, 11, 1)
DAY_6 = date(2026, 11, 6)


def compute_now(session: Session, cid: uuid.UUID, period: str) -> None:
    """Synchronous stand-in for the Celery enqueue in tests."""
    service.compute_client_close(session, cid, period, today=DAY_1, actor="system")


def start(session: Session) -> dict[str, PeriodClose]:
    closes = service.start_period_close(session, PERIOD, actor="test", enqueue=compute_now)
    return {c.client_id.hex: c for c in closes}


def close_of(session: Session, cid: str) -> PeriodClose:
    return session.scalars(select(PeriodClose).where(PeriodClose.client_id == uuid.UUID(cid))).one()


def alerts_of(session: Session, close: PeriodClose) -> dict[AlertType, Severity]:
    rows = session.scalars(
        select(CloseAlert).where(CloseAlert.close_id == close.id, CloseAlert.present.is_(True))
    )
    return {a.type: a.severity for a in rows}


def onboarded(api: TestClient) -> tuple[str, str]:
    martina, mateo = client_id(api, "Martina"), client_id(api, "Mateo")
    onboard(api, martina)
    onboard(api, mateo)
    return martina, mateo


def test_only_active_clients_get_a_close(seeded: Session, api: TestClient) -> None:
    onboard(api, client_id(api, "Martina"))
    assert len(start(seeded)) == 1


def test_day_1_leaves_martina_in_review_and_mateo_ready(seeded: Session, api: TestClient) -> None:
    martina, mateo = onboarded(api)
    start(seeded)
    m = close_of(seeded, martina)
    assert m.status is CloseStatus.IN_REVIEW
    assert alerts_of(seeded, m) == {
        AlertType.UNBILLED_COLLECTION: Severity.BLOCKING,
        AlertType.UNCLASSIFIED: Severity.WAITING,
        AlertType.NEAR_CAP: Severity.INFO,
    }
    assert m.result is not None and m.result["cap_usage_pct"] == "83.2"
    g = close_of(seeded, mateo)
    assert g.status is CloseStatus.READY and alerts_of(seeded, g) == {}


def test_recompute_without_changes_keeps_the_version(seeded: Session, api: TestClient) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    before = close_of(seeded, martina)
    version, digest = before.version, before.inputs_hash
    compute_now(seeded, uuid.UUID(martina), PERIOD)
    after = close_of(seeded, martina)
    assert (after.version, after.inputs_hash) == (version, digest)


def test_invoicing_after_day_1_leaves_only_the_user_question(
    seeded: Session, api: TestClient
) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    prompts = api.get(f"/api/v1/clients/{martina}/prompts").json()
    movement = next(p["movement_id"] for p in prompts if p["kind"] == "invoice_this")
    api.post(f"/api/v1/clients/{martina}/movements/{movement}/invoice", json={}, headers=ACTOR)
    assert close_of(seeded, martina).dirty
    compute_now(seeded, uuid.UUID(martina), PERIOD)
    assert close_of(seeded, martina).status is CloseStatus.PENDING_DATA


def test_unanswered_question_blocks_after_day_5(seeded: Session, api: TestClient) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    assert service.expire_pending_questions(seeded, PERIOD, actor="test") == 1
    service.compute_client_close(seeded, uuid.UUID(martina), PERIOD, today=DAY_6, actor="system")
    assert alerts_of(seeded, close_of(seeded, martina))[AlertType.UNCLASSIFIED] is Severity.BLOCKING
    # The recompute (under the client lock) is what expires the question.
    statuses = seeded.scalars(select(UserPrompt.status).where(UserPrompt.kind == PromptKind.WHO_IS))
    assert list(statuses) == [PromptStatus.EXPIRED]


def test_inbox_and_detail_endpoints(seeded: Session, api: TestClient) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    inbox = api.get("/api/v1/period-closes", params={"period": PERIOD}).json()
    assert inbox["started"] and inbox["counts"]["IN_REVIEW"] == 1 and inbox["counts"]["READY"] == 1
    first = inbox["rows"][0]
    assert first["client_id"] == martina  # in review goes first
    detail = api.get(f"/api/v1/period-closes/{first['close_id']}").json()
    assert detail["result"]["monthly_fee_ars"] == "58300.00"
    assert len(detail["movements"]) == 8 and len(detail["invoices"]) == 2
    assert any(step["label"].startswith("Acumulado 12 meses") for step in detail["result"]["trace"])


def test_inbox_is_empty_before_day_1(seeded: Session, api: TestClient) -> None:
    inbox = api.get("/api/v1/period-closes", params={"period": PERIOD}).json()
    assert inbox["started"] is False and inbox["rows"] == []


def test_inbox_paginates_and_filters_with_totals(seeded: Session, api: TestClient) -> None:
    onboarded(api)
    start(seeded)
    page = api.get("/api/v1/period-closes", params={"period": PERIOD, "limit": 1}).json()
    assert (page["total"], page["filtered_total"], len(page["rows"])) == (2, 2, 1)
    assert page["rows"][0]["status"] == "IN_REVIEW"  # priority order in SQL
    assert page["blocking_alerts"] == 1
    ready = api.get("/api/v1/period-closes", params={"period": PERIOD, "status": "READY"}).json()
    assert [r["status"] for r in ready["rows"]] == ["READY"] and ready["filtered_total"] == 1


def test_progress_counts_computed_closes(seeded: Session, api: TestClient) -> None:
    onboarded(api)
    start(seeded)
    progress = api.get("/api/v1/period-closes/progress", params={"period": PERIOD}).json()
    assert (progress["total"], progress["computed"], progress["dirty"]) == (2, 2, 0)
