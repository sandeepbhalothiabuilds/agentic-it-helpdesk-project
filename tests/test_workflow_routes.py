from __future__ import annotations

from fastapi.testclient import TestClient

from app.backend.api import routes_chat, routes_retrieval, routes_workflow
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


def test_retrieve_route_uses_search_knowledge(monkeypatch):
    captured: dict[str, str] = {}

    def fake_search_knowledge(query: str, workflow: str, top_k: int = 3, **kwargs):
        captured["query"] = query
        captured["workflow"] = workflow
        captured["top_k"] = str(top_k)
        return {
            "query": query,
            "workflow": workflow,
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "source": "runbook",
                    "document_name": "runbook",
                    "source_document": "runbook",
                    "workflow": workflow,
                    "score": 0.97,
                    "text": "Reset the password using the IAM tool.",
                    "metadata": {},
                }
            ],
            "source": "db",
        }

    monkeypatch.setattr(routes_retrieval, "search_knowledge", fake_search_knowledge)

    client = TestClient(app)
    response = client.post(
        "/retrieve",
        json={"query": "reset password", "workflow": "password_reset"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "password_reset"
    assert payload["results"][0]["chunk_id"] == "chunk-1"
    assert captured == {
        "query": "reset password",
        "workflow": "password_reset",
        "top_k": "3",
    }


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
