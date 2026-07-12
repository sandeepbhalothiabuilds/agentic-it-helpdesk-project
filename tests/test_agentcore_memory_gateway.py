from __future__ import annotations

from datetime import datetime

from app.backend.agentcore import gateway, memory
from app.backend.agents import execution_agent
from app.backend.services import preflight_service


class DummyMemoryClient:
    def __init__(self):
        self.request = None

    def create_event(self, **kwargs):
        self.request = kwargs
        return {"event": {"id": "evt-123"}, "ResponseMetadata": {"HTTPStatusCode": 200}}


class DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def test_agentcore_memory_records_conversation_turn(monkeypatch):
    dummy = DummyMemoryClient()
    monkeypatch.setattr(memory.settings, "agentcore_memory_enabled", "1")
    monkeypatch.setattr(memory.settings, "agentcore_memory_id", "mem-123")
    monkeypatch.setattr(memory.settings, "agentcore_memory_write_events", "1")
    monkeypatch.setattr(memory.settings, "agentcore_memory_actor_prefix", "employee")
    monkeypatch.setattr(memory, "_data_client", lambda: dummy)

    result = memory.record_conversation_turn(
        employee_id="E10231",
        session_id="REQ-123",
        user_message="unlock my account",
        assistant_message="Please confirm.",
    )

    assert result["ok"] is True
    assert result["event_id"] == "evt-123"
    assert dummy.request["memoryId"] == "mem-123"
    assert dummy.request["actorId"] == "employee_E10231"
    assert dummy.request["sessionId"] == "REQ-123"
    assert isinstance(dummy.request["eventTimestamp"], datetime)
    assert dummy.request["payload"][0]["conversational"]["role"] == "USER"
    assert dummy.request["payload"][1]["conversational"]["role"] == "ASSISTANT"


def test_agentcore_memory_skips_when_disabled(monkeypatch):
    monkeypatch.setattr(memory.settings, "agentcore_memory_enabled", "0")

    result = memory.record_conversation_turn(
        employee_id="E10231",
        session_id="REQ-123",
        user_message="hello",
        assistant_message="hi",
    )

    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["reason"] == "memory_disabled"


def test_agentcore_gateway_invokes_tool_with_identity_headers(monkeypatch):
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        captured["timeout"] = timeout
        return DummyResponse({"status": "Completed", "message": "unlocked", "metadata": {"trace_id": "abc"}})

    monkeypatch.setattr(gateway.settings, "agentcore_gateway_enabled", "1")
    monkeypatch.setattr(gateway.settings, "agentcore_gateway_url", "https://gateway.example.com")
    monkeypatch.setattr(gateway.settings, "agentcore_gateway_tool_prefix", "tools")
    monkeypatch.setattr(gateway.settings, "agentcore_gateway_timeout_seconds", 12)
    monkeypatch.setattr(gateway.settings, "agentcore_gateway_bearer_token", "token-123")
    monkeypatch.setattr(gateway.settings, "agentcore_gateway_api_key", "api-key-123")
    monkeypatch.setattr(gateway.requests, "post", fake_post)

    result = gateway.invoke_gateway_tool(
        tool_name="unlock_account",
        tool_input={"employee_id": "E10231"},
        actor_id="E10231",
        request_id="REQ-123",
    )

    assert result["status"] == "Completed"
    assert result["message"] == "unlocked"
    assert result["tool_runtime"]["provider"] == "agentcore_gateway"
    assert captured["url"] == "https://gateway.example.com/tools/unlock_account"
    assert captured["headers"]["Authorization"] == "Bearer token-123"
    assert captured["headers"]["X-API-Key"] == "api-key-123"
    assert captured["headers"]["X-AgentCore-Actor-Id"] == "E10231"
    assert captured["json"]["input"] == {"employee_id": "E10231"}
    assert captured["timeout"] == 12


def test_execution_agent_prefers_gateway_tool_when_available(monkeypatch):
    def fake_gateway_tool(**kwargs):
        assert kwargs["tool_name"] == "unlock_account"
        assert kwargs["tool_input"]["employee_id"] == "E10231"
        return {"status": "Completed", "message": "gateway unlocked", "tool_runtime": {"provider": "agentcore_gateway"}}

    monkeypatch.setattr(execution_agent, "invoke_gateway_tool_if_configured", fake_gateway_tool)

    result, action_type = execution_agent._execute_tool_action(
        "account_unlock",
        "E10231",
        "REQ-123",
        {"user": {"user_id": "U1"}, "account": {}, "rule": {}},
    )

    assert action_type == "Account Unlock"
    assert result["message"] == "gateway unlocked"
    assert result["tool_runtime"]["provider"] == "agentcore_gateway"


def test_preflight_requires_memory_id_when_memory_enabled(monkeypatch):
    monkeypatch.setattr(preflight_service.settings, "database_url_env", "postgresql://user:secret@host/db")
    monkeypatch.setattr(preflight_service.settings, "db_password", "")
    monkeypatch.setattr(preflight_service.settings, "llm_provider", "mistral")
    monkeypatch.setattr(preflight_service.settings, "mistral_api_key", "secret")
    monkeypatch.setattr(preflight_service.settings, "agent_runtime_provider", "local")
    monkeypatch.setattr(preflight_service.settings, "agentcore_memory_enabled", "1")
    monkeypatch.setattr(preflight_service.settings, "agentcore_memory_id", "")
    monkeypatch.setattr(preflight_service.settings, "agentcore_gateway_enabled", "0")
    monkeypatch.setattr(preflight_service.settings, "agentcore_identity_enabled", "0")
    monkeypatch.setattr(preflight_service.settings, "require_api_key", "0")
    monkeypatch.setattr(preflight_service.settings, "kb_storage_backend", "local")
    monkeypatch.setattr(preflight_service.settings, "kb_storage_root", "data/knowledge_base/uploads")

    result = preflight_service._check_configuration()

    assert result["status"] == "error"
    assert "Set AGENTCORE_MEMORY_ID" in result["details"]["errors"][0]
