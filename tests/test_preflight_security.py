from __future__ import annotations

from fastapi.testclient import TestClient

from app.backend.config import settings
from app.backend.main import app
from app.backend.services import preflight_service


class DummyResult:
    def __init__(self, value=1):
        self.value = value

    def scalar(self):
        return self.value


class DummyDB:
    def execute(self, statement, params=None):
        sql = str(statement)
        if "knowledge_documents" in sql:
            return DummyResult(2)
        if "document_chunks" in sql:
            return DummyResult(8)
        return DummyResult(1)


def test_request_id_header_is_preserved():
    client = TestClient(app)

    response = client.get("/health", headers={"X-Request-ID": "REQ-UNIT-TEST"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "REQ-UNIT-TEST"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_api_key_guard_blocks_protected_endpoint(monkeypatch):
    monkeypatch.setattr(settings, "require_api_key", "1")
    monkeypatch.setattr(settings, "api_key", "expected-secret")

    client = TestClient(app)
    response = client.get("/dashboard")

    assert response.status_code == 401
    assert response.json()["status"] == "error"


def test_api_key_guard_allows_public_health_without_key(monkeypatch):
    monkeypatch.setattr(settings, "require_api_key", "1")
    monkeypatch.setattr(settings, "api_key", "expected-secret")

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_config_is_redacted():
    client = TestClient(app)

    response = client.get("/health/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "config" in payload
    config = payload["config"]
    assert "mistral_api_key" not in config
    assert "db_password" not in config
    assert "database_url_redacted" in config


def test_preflight_service_reports_ready_when_checks_pass(monkeypatch):
    monkeypatch.setattr(preflight_service.settings, "database_url_env", "postgresql://user:secret@host/db")
    monkeypatch.setattr(preflight_service.settings, "db_password", "")
    monkeypatch.setattr(preflight_service.settings, "require_api_key", "0")
    monkeypatch.setattr(preflight_service.settings, "mistral_disable", "1")

    payload = preflight_service.run_preflight_checks(DummyDB())

    assert payload["status"] == "ok"
    assert payload["ready"] is True
    assert payload["summary"]["error"] == 0
    assert any(check["name"] == "database_connection" for check in payload["checks"])
