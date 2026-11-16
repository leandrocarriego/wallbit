"""Steps 0 and 1 of the demo through the API: enroll, link ARCA, get prompts, act on them."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from app.modules.enrollment.service import CURRENT_CONSENT_VERSION

ACTOR = {"X-Actor": "client:test"}


def client_id(api: TestClient, name: str) -> str:
    return next(
        c["id"] for c in api.get("/api/v1/clients").json() if c["full_name"].startswith(name)
    )


def onboard(api: TestClient, cid: str) -> dict[str, Any]:
    body = {"consent_version": CURRENT_CONSENT_VERSION, "accepted": True}
    assert (
        api.post(f"/api/v1/clients/{cid}/enrollment", json=body, headers=ACTOR).status_code == 200
    )
    response = api.post(f"/api/v1/clients/{cid}/arca-link", headers=ACTOR)
    assert response.status_code == 200
    data: dict[str, Any] = response.json()
    return data


def test_seeded_users_start_with_the_offer(seeded: Session, api: TestClient) -> None:
    home = api.get(f"/api/v1/clients/{client_id(api, 'Martina')}/home").json()
    assert home["stage"] == "offer" and home["prompts"] == []


def test_arca_link_is_rejected_before_enrolling(seeded: Session, api: TestClient) -> None:
    response = api.post(f"/api/v1/clients/{client_id(api, 'Martina')}/arca-link", headers=ACTOR)
    assert response.status_code == 409
    assert response.json()["code"] == "not_enrolled"


def test_enrollment_requires_consent(seeded: Session, api: TestClient) -> None:
    body = {"consent_version": CURRENT_CONSENT_VERSION, "accepted": False}
    response = api.post(f"/api/v1/clients/{client_id(api, 'Martina')}/enrollment", json=body)
    assert response.status_code == 409 and response.json()["code"] == "consent_required"


def test_linking_arca_reads_category_imports_invoices_and_asks_martina(
    seeded: Session, api: TestClient
) -> None:
    data = onboard(api, client_id(api, "Martina"))
    assert data["client"]["category"] == "D"
    assert len(data["imported"]) == 13  # 11 previous months + 2 in October
    prompts = {p["kind"]: p["payload"] for p in data["prompts"]}
    assert prompts["who_is"]["counterparty"] == "J. Pérez"
    assert prompts["who_is"]["suggestion"]["category"] == "personal_transfer"
    assert prompts["invoice_this"]["amount"] == "1200.00"


def test_mateo_has_nothing_to_do_after_linking(seeded: Session, api: TestClient) -> None:
    assert onboard(api, client_id(api, "Mateo"))["prompts"] == []


def test_invoicing_from_the_app_matches_the_payment_and_closes_the_prompt(
    seeded: Session, api: TestClient
) -> None:
    cid = client_id(api, "Martina")
    prompts = onboard(api, cid)["prompts"]
    movement = next(p["movement_id"] for p in prompts if p["kind"] == "invoice_this")
    invoice = api.post(
        f"/api/v1/clients/{cid}/movements/{movement}/invoice", json={}, headers=ACTOR
    )
    assert invoice.status_code == 200 and invoice.json()["source"] == "arca_issued"
    remaining = [p["kind"] for p in api.get(f"/api/v1/clients/{cid}/prompts").json()]
    assert remaining == ["who_is"]
    matched = seeded.execute(
        text("SELECT source FROM movement_classifications WHERE movement_id = :m"), {"m": movement}
    ).scalar_one()
    assert matched == "invoice_match"


def test_answering_who_is_declares_the_counterparty(seeded: Session, api: TestClient) -> None:
    cid = client_id(api, "Martina")
    prompts = onboard(api, cid)["prompts"]
    who = next(p for p in prompts if p["kind"] == "who_is")
    response = api.post(
        f"/api/v1/clients/{cid}/prompts/{who['id']}/answer",
        json={"answer": "family"},
        headers=ACTOR,
    )
    assert [p["kind"] for p in response.json()] == ["invoice_this"]
    category = seeded.execute(
        text("SELECT category FROM movement_classifications WHERE movement_id = :m"),
        {"m": who["movement_id"]},
    ).scalar_one()
    assert category == "personal_transfer"


def test_every_user_action_is_audited(seeded: Session, api: TestClient) -> None:
    onboard(api, client_id(api, "Martina"))
    actions = set(seeded.scalars(select(AuditEvent.action)))
    assert {
        "client.enrolled",
        "client.arca_linked",
        "invoices.synced_from_arca",
        "classification.reclassified",
    } <= actions
