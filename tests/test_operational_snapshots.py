from __future__ import annotations

from types import SimpleNamespace

from app.backend.services import admin_service, dashboard_service


class DummyDB:
    pass


class DummyResult:
    def __init__(self, rows=None, scalar_value=None):
        self._rows = rows or []
        self._scalar_value = scalar_value

    def scalar(self):
        return self._scalar_value

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None


def test_dashboard_snapshot_includes_status_and_last_indexed(monkeypatch):
    def fake_scalar(db, sql, params=None):
        mapping = {
            "workflow_sessions": 7,
            "service_tickets": 4,
            "document_chunks": 12,
            "retrieval_logs": 9,
            "workflow_events": 15,
            "audit_logs": 3,
        }
        for needle, value in mapping.items():
            if needle in sql:
                return value
        return 0

    def fake_rows(db, sql, params=None):
        if "MAX(updated_at) AS last_indexed" in sql:
            return [{"last_indexed": "2026-07-05T12:00:00+00:00"}]
        if "FROM case4.workflow_sessions" in sql and "GROUP BY" in sql:
            return [
                {
                    "intent": "password_reset",
                    "status": "completed",
                    "request_count": 5,
                    "last_updated": "2026-07-05T11:00:00+00:00",
                }
            ]
        if "FROM case4.workflow_sessions" in sql:
            return [
                {
                    "request_id": "REQ-1",
                    "employee_id": "E10231",
                    "intent": "password_reset",
                    "current_node": "response",
                    "status": "completed",
                    "needs_confirmation": False,
                    "ticket_id": "INC-1",
                    "created_at": "2026-07-05T10:00:00+00:00",
                    "updated_at": "2026-07-05T10:05:00+00:00",
                }
            ]
        if "FROM case4.service_tickets" in sql:
            return [
                {
                    "ticket_id": "INC-1",
                    "employee_id": "E10231",
                    "full_name": "Alex Doe",
                    "status": "open",
                    "priority": "high",
                    "category": "password_reset",
                    "summary": "Reset password ticket",
                    "assigned_group": "service-desk",
                    "last_updated": "2026-07-05T10:05:00+00:00",
                }
            ]
        if "FROM case4.audit_logs" in sql:
            return [
                {
                    "audit_id": "AUD-1",
                    "request_id": "REQ-1",
                    "stage": "execution",
                    "status": "ok",
                    "message": "Completed",
                    "created_at": "2026-07-05T10:06:00+00:00",
                    "created_by": "system",
                }
            ]
        if "FROM case4.workflow_events" in sql:
            return [
                {
                    "event_id": "EVT-1",
                    "request_id": "REQ-1",
                    "employee_id": "E10231",
                    "node_name": "classify",
                    "stage": "intent_classification",
                    "outcome": "completed",
                    "created_at": "2026-07-05T10:01:00+00:00",
                }
            ]
        return []

    monkeypatch.setattr(dashboard_service, "_scalar", fake_scalar)
    monkeypatch.setattr(dashboard_service, "_rows", fake_rows)

    payload = dashboard_service.get_dashboard_snapshot(DummyDB())

    assert payload["status"] == "ok"
    assert payload["generated_at"]
    assert payload["summary"]["active_requests"] == 7
    assert payload["summary"]["last_indexed"] == "2026-07-05T12:00:00+00:00"
    assert payload["workflow_breakdown"][0]["intent"] == "password_reset"
    assert payload["recent_requests"][0]["request_id"] == "REQ-1"
    assert payload["recent_tickets"][0]["ticket_id"] == "INC-1"


def test_admin_status_redacts_database_url_and_reports_health(monkeypatch):
    fake_settings = SimpleNamespace(
        app_env="local",
        mistral_model="mistral-small-latest",
        mistral_disable="0",
        mistral_api_key="secret",
        database_url="postgresql+psycopg2://service_desk:secret@db.example.com:5432/postgres?sslmode=require",
    )

    def fake_scalar(db, sql, params=None):
        return 2

    def fake_probe_ollama():
        return {"ok": True, "message": "Ollama is reachable", "base_url": "http://localhost:11434", "models": []}

    monkeypatch.setattr(admin_service, "settings", fake_settings)
    monkeypatch.setattr(admin_service, "_scalar", fake_scalar)
    monkeypatch.setattr(admin_service, "_probe_ollama", fake_probe_ollama)

    payload = admin_service.get_system_status(DummyDB())

    assert payload["status"] == "ok"
    assert payload["generated_at"]
    assert payload["health"]["database"]["ok"] is True
    assert payload["health"]["ollama"]["ok"] is True
    assert payload["counts"]["knowledge_documents"] == 2
    assert payload["config"]["database_url_redacted"] == "postgresql+psycopg2://db.example.com:5432/postgres?sslmode=require"
    assert payload["proof"]["database_ok"] is True
    assert payload["proof"]["ollama_ok"] is True