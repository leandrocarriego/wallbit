"""Demo reset from the console: the walkthrough can be run again from the start."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.audit.models import AuditEvent
from tests.integration.test_user_flow import client_id, onboard


def test_reset_brings_the_demo_back_to_the_start(seeded: Session, api: TestClient) -> None:
    onboard(api, client_id(api, "Martina"))
    assert api.post("/api/v1/demo/day-1", headers={"X-Actor": "accountant-demo"}).status_code == 200

    assert api.post("/api/v1/demo/reset", headers={"X-Actor": "accountant-demo"}).status_code == 204

    clients = api.get("/api/v1/clients").json()
    assert sorted(c["full_name"] for c in clients) == ["Martina Ríos", "Mateo Giménez"]
    home = api.get(f"/api/v1/clients/{client_id(api, 'Martina')}/home").json()
    assert home["stage"] == "offer" and home["prompts"] == []
    assert api.get("/api/v1/demo/clock").json() == {"today": "2026-10-31"}
    actions = seeded.scalars(select(AuditEvent.action)).all()
    assert actions == ["demo.reset"]
