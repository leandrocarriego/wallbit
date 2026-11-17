"""Movements arriving from Wallbit are classified on arrival and ask the user right away."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.ingestion.models import Movement

from .test_closing import onboarded
from .test_user_flow import client_id

PAYMENT = {
    "occurred_at": datetime(2026, 10, 27, 18, tzinfo=UTC).isoformat(),
    "type": "incoming_transfer",
    "direction": "in",
    "amount": "250.00",
    "currency": "USD",
    "fx_rate_ars": "1450",
    "origin_country": "AR",
}


def ingest(api: TestClient, cid: str, external_id: str, counterparty: str) -> dict:  # type: ignore[type-arg]
    body = {**PAYMENT, "client_id": cid, "external_id": external_id, "counterparty": counterparty}
    response = api.post("/api/v1/movements", json=body, headers={"X-Actor": "wallbit-core"})
    assert response.status_code == 200
    return response.json()  # type: ignore[no-any-return]


def test_payment_from_an_unknown_person_asks_who_is_it(seeded: Session, api: TestClient) -> None:
    _, mateo = onboarded(api)
    data = ingest(api, mateo, "ext-1", "R. Ibáñez")
    asked = [p for p in data["prompts"] if p["movement_id"] == data["movement_id"]]
    assert data["created"] and data["period"] == "2026-10"
    assert [p["kind"] for p in asked] == ["who_is"]


def test_redelivered_event_is_stored_once(seeded: Session, api: TestClient) -> None:
    _, mateo = onboarded(api)
    first = ingest(api, mateo, "ext-2", "R. Ibáñez")
    again = ingest(api, mateo, "ext-2", "R. Ibáñez")
    assert again["movement_id"] == first["movement_id"] and not again["created"]
    stored = seeded.scalar(
        select(func.count()).select_from(Movement).where(Movement.external_id == "ext-2")
    )
    assert stored == 1


def test_client_without_the_service_is_not_classified_yet(seeded: Session, api: TestClient) -> None:
    data = ingest(api, client_id(api, "Martina"), "ext-3", "R. Ibáñez")
    assert data["created"] and data["prompts"] == []
