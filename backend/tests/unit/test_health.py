from fastapi.testclient import TestClient

from app import main


def test_health_returns_ok_when_db_is_reachable(monkeypatch) -> None:
    monkeypatch.setattr(main, "ping_db", lambda: True)
    response = TestClient(main.app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_metrics_exposes_prometheus_format() -> None:
    response = TestClient(main.app).get("/metrics")
    assert response.status_code == 200
    assert "http_requests_total" in response.text
