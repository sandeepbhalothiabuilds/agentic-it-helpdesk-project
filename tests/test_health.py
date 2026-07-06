from __future__ import annotations

from fastapi.testclient import TestClient

from app.backend.main import app


def test_health_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "agentic-it-service-desk"
    assert payload["environment"]
    assert payload["timestamp"]


def test_root_endpoint_returns_ok():
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "agentic-it-service-desk"
    assert payload["environment"]
    assert payload["docs"] == "/docs"
    assert payload["health"] == "/health"
    assert payload["ready"] == "/ready"
