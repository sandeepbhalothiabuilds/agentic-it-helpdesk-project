from __future__ import annotations

from fastapi.testclient import TestClient

from app.backend.api import routes_chat, routes_workflow
from app.backend.main import app


def test_chat_route_delegates_to_workflow_handler(monkeypatch):
    captured: dict[str, object] = {}

    def fake_handle_request(
        message: str,
        employee_id: str,
        db,
        confirm: bool = False,
        request_id: str | None = None,
    ):
        captured["message"] = message
        captured["employee_id"] = employee_id
        captured["confirm"] = confirm
        captured["request_id"] = request_id
        return {
            "status": "completed",
            "message": "Action completed.",
            "request_id": request_id or "REQ-TEST",
            "workflow": "password_reset",
        }

    monkeypatch.setattr(routes_chat, "handle_request", fake_handle_request)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json={
            "message": "reset my password",
            "employee_id": "E10231",
            "confirm": False,
            "request_id": "REQ-123",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["message"] == "Action completed."
    assert payload["request_id"] == "REQ-123"
    assert captured == {
        "message": "reset my password",
        "employee_id": "E10231",
        "confirm": False,
        "request_id": "REQ-123",
    }



def test_chat_route_rejects_missing_employee_id(monkeypatch):
    called = False

    def fake_handle_request(*args, **kwargs):
        nonlocal called
        called = True
        return {"status": "completed"}

    monkeypatch.setattr(routes_chat, "handle_request", fake_handle_request)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json={"message": "unlock my account", "confirm": False},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Employee ID is required. Enter an employee ID in the UI before submitting a request."
    assert called is False


def test_chat_route_rejects_blank_employee_id(monkeypatch):
    called = False

    def fake_handle_request(*args, **kwargs):
        nonlocal called
        called = True
        return {"status": "completed"}

    monkeypatch.setattr(routes_chat, "handle_request", fake_handle_request)

    client = TestClient(app)
    response = client.post(
        "/chat",
        json={"message": "unlock my account", "employee_id": "   ", "confirm": False},
    )

    assert response.status_code == 400
    assert response.json()["message"] == "Employee ID is required. Enter an employee ID in the UI before submitting a request."
    assert called is False

def test_workflow_history_endpoint_returns_history(monkeypatch):
    monkeypatch.setattr(
        routes_workflow,
        "get_workflow_session",
        lambda db, request_id: {"request_id": request_id, "status": "completed"},
    )
    monkeypatch.setattr(
        routes_workflow,
        "list_workflow_events",
        lambda db, request_id, limit=100: [
            {
                "event_id": "evt-1",
                "request_id": request_id,
                "node_name": "classify",
                "stage": "intent_classification",
                "outcome": "completed",
            }
        ],
    )
    monkeypatch.setattr(
        routes_workflow,
        "list_retrieval_logs",
        lambda db, request_id, limit=50: [
            {
                "log_id": "log-1",
                "request_id": request_id,
                "query_text": "reset password",
            }
        ],
    )

    client = TestClient(app)
    response = client.get("/workflow/history/REQ-123")

    assert response.status_code == 200
    payload = response.json()
    assert payload["session"]["request_id"] == "REQ-123"
    assert payload["events"][0]["node_name"] == "classify"
    assert payload["retrieval_logs"][0]["query_text"] == "reset password"


def test_build_chunks_script_runs_dry_run(monkeypatch, capsys):
    from scripts import build_chunks

    class DummyDB:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_snapshot(db, chunk_limit=50):
        return {
            "summary": {
                "active_documents": 2,
                "active_revisions": 3,
                "active_chunks": 7,
                "total_chunks": 7,
            }
        }

    monkeypatch.setattr(build_chunks, "SessionLocal", lambda: DummyDB())
    monkeypatch.setattr(build_chunks, "get_knowledge_base_snapshot", fake_snapshot)
    monkeypatch.setattr(build_chunks, "refresh_knowledge_base", lambda db: {"status": "refreshed"})

    exit_code = build_chunks.main(["--dry-run"])
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "Before:" in captured
    assert "active_documents=2" in captured
    assert "Refresh result:" not in captured



def test_workflow_sessions_endpoint_returns_recent_sessions(monkeypatch):
    monkeypatch.setattr(
        routes_workflow,
        "list_workflow_sessions",
        lambda db, employee_id=None, status=None, limit=50: [
            {
                "request_id": "REQ-123",
                "employee_id": employee_id or "E10231",
                "intent": "password_reset",
                "status": status or "completed",
                "current_node": "response",
            }
        ],
    )

    client = TestClient(app)
    response = client.get("/workflow/sessions", params={"employee_id": "E10231", "status": "completed", "limit": 10})

    assert response.status_code == 200
    payload = response.json()
    assert payload["sessions"][0]["request_id"] == "REQ-123"
    assert payload["sessions"][0]["employee_id"] == "E10231"
    assert payload["sessions"][0]["status"] == "completed"
