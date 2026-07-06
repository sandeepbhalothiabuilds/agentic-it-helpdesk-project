from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.backend.api import routes_knowledge_base
from app.backend.main import app


def test_knowledge_base_search_route_delegates(monkeypatch):
    captured: dict[str, object] = {}

    def fake_search_knowledge_base(db, *, query=None, workflow=None, active_only=True, limit=50):
        captured["query"] = query
        captured["workflow"] = workflow
        captured["active_only"] = active_only
        captured["limit"] = limit
        return {
            "status": "ok",
            "query": query,
            "workflow": workflow,
            "summary": {"document_count": 1, "revision_count": 1, "chunk_count": 1},
            "documents": [{"source_document": "password_runbook"}],
            "revisions": [{"document_id": "DOC-1"}],
            "chunks": [{"chunk_id": "CHUNK-1"}],
        }

    monkeypatch.setattr(routes_knowledge_base, "search_knowledge_base", fake_search_knowledge_base)

    client = TestClient(app)
    response = client.get(
        "/knowledge-base/search",
        params={
            "query": "password",
            "workflow": "password_reset",
            "active_only": "true",
            "limit": 25,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["document_count"] == 1
    assert captured == {
        "query": "password",
        "workflow": "password_reset",
        "active_only": True,
        "limit": 25,
    }


def test_knowledge_base_update_route_delegates(monkeypatch):
    captured: dict[str, object] = {}

    def fake_update_document_metadata(db, document_id, *, workflow=None, uploaded_by=None, updated_by="streamlit"):
        captured["document_id"] = document_id
        captured["workflow"] = workflow
        captured["uploaded_by"] = uploaded_by
        captured["updated_by"] = updated_by
        return {
            "status": "updated",
            "document": {
                "document_id": document_id,
                "workflow": workflow,
                "uploaded_by": uploaded_by,
            },
        }

    monkeypatch.setattr(routes_knowledge_base, "update_document_metadata", fake_update_document_metadata)

    client = TestClient(app)
    response = client.patch(
        "/knowledge-base/documents/DOC-123",
        json={
            "workflow": "vpn_reenable",
            "uploaded_by": "operator",
            "updated_by": "admin",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "updated"
    assert captured == {
        "document_id": "DOC-123",
        "workflow": "vpn_reenable",
        "uploaded_by": "operator",
        "updated_by": "admin",
    }


def test_knowledge_base_activate_and_deactivate_routes(monkeypatch):
    calls: list[tuple[str, str, str]] = []

    def fake_activate(db, document_id, *, updated_by="streamlit"):
        calls.append(("activate", document_id, updated_by))
        return {"status": "activated", "document_id": document_id}

    def fake_deactivate(db, document_id, *, updated_by="streamlit"):
        calls.append(("deactivate", document_id, updated_by))
        return {"status": "deactivated", "document_id": document_id}

    monkeypatch.setattr(routes_knowledge_base, "activate_document_revision", fake_activate)
    monkeypatch.setattr(routes_knowledge_base, "deactivate_document_revision", fake_deactivate)

    client = TestClient(app)
    activate_response = client.post(
        "/knowledge-base/documents/DOC-123/activate",
        json={"updated_by": "operator"},
    )
    deactivate_response = client.post(
        "/knowledge-base/documents/DOC-123/deactivate",
        json={"updated_by": "operator"},
    )

    assert activate_response.status_code == 200
    assert deactivate_response.status_code == 200
    assert activate_response.json()["status"] == "activated"
    assert deactivate_response.json()["status"] == "deactivated"
    assert calls == [
        ("activate", "DOC-123", "operator"),
        ("deactivate", "DOC-123", "operator"),
    ]


def test_knowledge_base_download_route_returns_file(monkeypatch, tmp_path):
    stored_file = tmp_path / "runbook.txt"
    stored_file.write_text("reset password runbook", encoding="utf-8")

    def fake_get_document_file_info(db, document_id):
        return {
            "document_id": document_id,
            "source_document": "runbook",
            "original_filename": "runbook.txt",
            "mime_type": "text/plain",
            "storage_path": Path(stored_file),
            "exists": True,
        }

    monkeypatch.setattr(routes_knowledge_base, "get_document_file_info", fake_get_document_file_info)

    client = TestClient(app)
    response = client.get("/knowledge-base/documents/DOC-123/download")

    assert response.status_code == 200
    assert response.content == b"reset password runbook"
    assert response.headers["content-type"].startswith("text/plain")
