from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi.testclient import TestClient

from app.backend.api import routes_retrieval
from app.backend.main import app
from app.backend.services import retrieval_service


@dataclass
class DummyChunk:
    chunk_id: str
    source_document: str
    workflow: str
    chunk_index: int
    chunk_text: str
    embedding_json: list[float]
    chunk_metadata: dict[str, Any]


class DummyQuery:
    def __init__(self, rows: list[DummyChunk]):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, value: int):
        self.rows = self.rows[:value]
        return self

    def all(self):
        return self.rows


class DummySession:
    def __init__(self, rows: list[DummyChunk]):
        self.rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, model):
        return DummyQuery(list(self.rows))


def test_retrieve_route_uses_search_knowledge(monkeypatch):
    captured: dict[str, str] = {}

    def fake_search_knowledge(
        query: str,
        workflow: str,
        top_k: int = 3,
        *,
        min_score: float = 0.0,
        candidate_limit: int = 500,
        include_general: bool = True,
    ):
        captured["query"] = query
        captured["workflow"] = workflow
        captured["top_k"] = str(top_k)
        captured["min_score"] = str(min_score)
        captured["candidate_limit"] = str(candidate_limit)
        captured["include_general"] = str(include_general)
        return {
            "query": query,
            "workflow": workflow,
            "retrieval_strategy": "hybrid",
            "confidence": "high",
            "results": [
                {
                    "chunk_id": "chunk-1",
                    "chunk_index": 0,
                    "source": "runbook",
                    "document_name": "runbook",
                    "source_document": "runbook",
                    "workflow": workflow,
                    "score": 0.97,
                    "semantic_score": 0.95,
                    "lexical_score": 0.8,
                    "confidence": "high",
                    "citation_label": "runbook#chunk-0",
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
        json={
            "query": "reset password",
            "workflow": "password_reset",
            "top_k": 4,
            "min_score": 0.2,
            "candidate_limit": 25,
            "include_general": False,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["workflow"] == "password_reset"
    assert payload["retrieval_strategy"] == "hybrid"
    assert payload["confidence"] == "high"
    assert payload["results"][0]["chunk_id"] == "chunk-1"
    assert payload["results"][0]["citation_label"] == "runbook#chunk-0"
    assert captured == {
        "query": "reset password",
        "workflow": "password_reset",
        "top_k": "4",
        "min_score": "0.2",
        "candidate_limit": "25",
        "include_general": "False",
    }


def test_search_knowledge_ranks_hybrid_results(monkeypatch):
    rows = [
        DummyChunk(
            chunk_id="chunk-low",
            source_document="vpn_runbook",
            workflow="vpn_reenable",
            chunk_index=0,
            chunk_text="VPN users should verify tunnel connectivity and certificate status.",
            embedding_json=[0.3, 0.1, 0.0],
            chunk_metadata={"revision_number": 1, "file_hash": "hash-low", "storage_path": "vpn.pdf"},
        ),
        DummyChunk(
            chunk_id="chunk-high",
            source_document="password_reset_runbook",
            workflow="password_reset",
            chunk_index=1,
            chunk_text="Reset password requests require identity verification before using the IAM reset tool.",
            embedding_json=[1.0, 0.0, 0.0],
            chunk_metadata={"revision_number": 2, "file_hash": "hash-high", "storage_path": "password.pdf"},
        ),
    ]

    monkeypatch.setattr(retrieval_service, "embed_text", lambda text: [1.0, 0.0, 0.0])
    monkeypatch.setattr(retrieval_service, "SessionLocal", lambda: DummySession(rows))

    payload = retrieval_service.search_knowledge(
        "reset my password",
        "password_reset",
        top_k=2,
        min_score=0.01,
    )

    assert payload["retrieval_strategy"] == "hybrid"
    assert payload["candidate_count"] == 2
    assert payload["result_count"] == 2
    assert payload["confidence"] in {"high", "medium"}
    assert payload["results"][0]["chunk_id"] == "chunk-high"
    assert payload["results"][0]["semantic_score"] > payload["results"][1]["semantic_score"]
    assert payload["results"][0]["lexical_score"] > 0
    assert payload["results"][0]["citation"]["revision_number"] == 2
    assert "workflow_match" in payload["results"][0]["match_reasons"]


def test_search_knowledge_falls_back_to_lexical_when_embedding_unavailable(monkeypatch):
    rows = [
        DummyChunk(
            chunk_id="chunk-1",
            source_document="account_lockout_playbook",
            workflow="account_unlock",
            chunk_index=0,
            chunk_text="For account lockout, verify identity and unlock the directory account.",
            embedding_json=[],
            chunk_metadata={},
        )
    ]

    monkeypatch.setattr(retrieval_service, "embed_text", lambda text: [])
    monkeypatch.setattr(retrieval_service, "SessionLocal", lambda: DummySession(rows))

    payload = retrieval_service.search_knowledge("unlock account", "account_unlock", top_k=1)

    assert payload["retrieval_strategy"] == "lexical"
    assert payload["result_count"] == 1
    assert payload["results"][0]["chunk_id"] == "chunk-1"
    assert payload["results"][0]["lexical_score"] > 0
    assert payload["results"][0]["semantic_score"] == 0
    assert payload["results"][0]["confidence"] in {"low", "medium", "high"}
