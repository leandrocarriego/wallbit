"""Accountant actions: resolve, classify, converse, approve (individual and batch)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.modules.alerts.engine import AlertType, CloseStatus
from app.modules.closing.models import CloseAlert, PeriodClose
from app.modules.notifications.models import Notification, NotificationStatus
from app.modules.review.models import CloseSnapshot

from .test_closing import close_of, onboarded, start

P = "/api/v1/period-closes"
ATTEST = {"attested": True}


def alert_id(session: Session, close: PeriodClose, kind: AlertType) -> str:
    alert = session.scalars(
        select(CloseAlert).where(CloseAlert.close_id == close.id, CloseAlert.type == kind)
    ).one()
    return str(alert.id)


def movement_of(api: TestClient, close: PeriodClose, counterparty: str) -> str:
    detail = api.get(f"{P}/{close.id}").json()
    return next(m["id"] for m in detail["movements"] if m["counterparty"] == counterparty)


def make_martina_ready(seeded: Session, api: TestClient) -> PeriodClose:
    martina, _ = onboarded(api)
    start(seeded)
    close = close_of(seeded, martina)
    unbilled = alert_id(seeded, close, AlertType.UNBILLED_COLLECTION)
    api.post(f"{P}/{close.id}/alerts/{unbilled}/resolve", json={"resolution": "Factura en trámite"})
    jp = movement_of(api, close, "J. Pérez")
    response = api.post(
        f"{P}/{close.id}/movements/{jp}/classify", json={"category": "personal_transfer"}
    )
    assert response.json()["status"] == "READY"
    return close


def test_blocked_close_cannot_be_approved(seeded: Session, api: TestClient) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    response = api.post(f"{P}/{close_of(seeded, martina).id}/approve", json=ATTEST)
    assert response.status_code == 409 and response.json()["code"] == "close_not_ready"


def test_approval_requires_the_attestation(seeded: Session, api: TestClient) -> None:
    close = make_martina_ready(seeded, api)
    response = api.post(f"{P}/{close.id}/approve", json={"attested": False})
    assert response.json()["code"] == "attestation_required"


def test_resolution_survives_recompute_and_undo_reopens(seeded: Session, api: TestClient) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    close = close_of(seeded, martina)
    unbilled = alert_id(seeded, close, AlertType.UNBILLED_COLLECTION)
    api.post(f"{P}/{close.id}/alerts/{unbilled}/resolve", json={})
    assert close_of(seeded, martina).status is CloseStatus.PENDING_DATA  # only J. Pérez left
    state = api.post(f"{P}/{close.id}/alerts/{unbilled}/reopen").json()
    assert state["status"] == "IN_REVIEW"


def test_approve_freezes_an_immutable_snapshot_and_queues_the_notice(
    seeded: Session, api: TestClient
) -> None:
    close = make_martina_ready(seeded, api)
    snapshot = api.post(f"{P}/{close.id}/approve", json=ATTEST).json()
    assert "Tenés que pagar $ 58.300 de monotributo antes del 20/11." in snapshot["message"]
    assert close_of(seeded, str(close.client_id)).status is CloseStatus.APPROVED
    notice = seeded.scalars(select(Notification)).one()
    assert notice.status is NotificationStatus.PENDING and notice.body == snapshot["message"]
    with pytest.raises(DBAPIError, match="inmutable"), seeded.begin_nested():
        seeded.execute(text("UPDATE close_snapshots SET message = 'otro'"))


def test_approved_close_is_not_recomputed_or_edited(seeded: Session, api: TestClient) -> None:
    close = make_martina_ready(seeded, api)
    api.post(f"{P}/{close.id}/approve", json=ATTEST)
    jp = movement_of(api, close, "J. Pérez")
    response = api.post(f"{P}/{close.id}/movements/{jp}/classify", json={"category": None})
    assert response.json()["code"] == "close_frozen"


def test_batch_approves_ready_closes_once_per_key(seeded: Session, api: TestClient) -> None:
    onboarded(api)
    start(seeded)
    headers = {"Idempotency-Key": "batch-test-1"}
    body = {"period": "2026-10", "attested": True}
    first = api.post(f"{P}/batch-approve", json=body, headers=headers).json()
    again = api.post(f"{P}/batch-approve", json=body, headers=headers).json()
    assert (first["approved"], first["replayed"]) == (1, False)  # only Mateo is ready
    assert (again["approved"], again["replayed"]) == (1, True)
    assert len(seeded.scalars(select(CloseSnapshot)).all()) == 1


def test_batch_requires_an_idempotency_key(seeded: Session, api: TestClient) -> None:
    response = api.post(f"{P}/batch-approve", json={"period": "2026-10", "attested": True})
    assert response.json()["code"] == "idempotency_key_required"


def test_conversation_reaches_the_user_and_back(seeded: Session, api: TestClient) -> None:
    martina, _ = onboarded(api)
    start(seeded)
    close = close_of(seeded, martina)
    unbilled = alert_id(seeded, close, AlertType.UNBILLED_COLLECTION)
    api.post(f"{P}/{close.id}/alerts/{unbilled}/messages", json={"body": "¿La facturaste?"})
    threads = api.get(f"/api/v1/clients/{martina}/conversations").json()
    assert threads[0]["messages"][0]["body"] == "¿La facturaste?"
    api.post(
        f"/api/v1/clients/{martina}/alerts/{unbilled}/messages",
        json={"body": "Ya la emití"},
        headers={"X-Actor": f"client:{martina}"},
    )
    authors = [m["author"] for m in api.get(f"{P}/{close.id}/alerts/{unbilled}/messages").json()]
    assert authors == ["accountant-demo", f"client:{martina}"]


def test_user_cannot_post_on_someone_elses_alert(seeded: Session, api: TestClient) -> None:
    martina, mateo = onboarded(api)
    start(seeded)
    unbilled = alert_id(seeded, close_of(seeded, martina), AlertType.UNBILLED_COLLECTION)
    response = api.post(
        f"/api/v1/clients/{mateo}/alerts/{unbilled}/messages", json={"body": "hola"}
    )
    assert response.status_code == 409
