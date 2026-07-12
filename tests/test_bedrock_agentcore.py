from __future__ import annotations

import json
from types import SimpleNamespace

from app.backend.agentcore import client as agentcore_client
from app.backend.agentcore import provider as agentcore_provider
from app.backend.llm import bedrock_client, provider as llm_provider
from app.backend.services import preflight_service


class DummyDB:
    pass


class DummyStreamingBody:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload


class DummyBedrockRuntimeClient:
    def __init__(self):
        self.request = None

    def converse(self, **kwargs):
        self.request = kwargs
        return {
            "output": {"message": {"content": [{"text": "bedrock response"}] }},
            "usage": {"inputTokens": 4, "outputTokens": 2},
            "metrics": {"latencyMs": 10},
            "stopReason": "end_turn",
        }


class DummyAgentCoreClient:
    def __init__(self):
        self.request = None

    def invoke_agent_runtime(self, **kwargs):
        self.request = kwargs
        return {
            "runtimeSessionId": kwargs.get("runtimeSessionId"),
            "traceId": kwargs.get("traceId"),
            "contentType": "application/json",
            "statusCode": 200,
            "response": DummyStreamingBody(json.dumps({"status": "completed", "message": "agentcore response"}).encode()),
        }


def test_bedrock_converse_formats_messages_and_extracts_trace(monkeypatch):
    dummy_client = DummyBedrockRuntimeClient()
    monkeypatch.setattr(bedrock_client.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(bedrock_client.settings, "bedrock_text_model_id", "test-model")
    monkeypatch.setattr(bedrock_client.settings, "bedrock_temperature", 0.2)
    monkeypatch.setattr(bedrock_client.settings, "bedrock_max_tokens", 128)
    monkeypatch.setattr(bedrock_client.settings, "bedrock_guardrail_identifier", "")
    monkeypatch.setattr(bedrock_client.settings, "bedrock_guardrail_version", "")
    monkeypatch.setattr(bedrock_client, "_runtime_client", lambda: dummy_client)

    text, trace = bedrock_client.converse_with_trace(
        [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello"},
        ]
    )

    assert text == "bedrock response"
    assert trace["provider"] == "bedrock"
    assert trace["model"] == "test-model"
    assert dummy_client.request["modelId"] == "test-model"
    assert dummy_client.request["system"] == [{"text": "You are helpful."}]
    assert dummy_client.request["messages"][0]["role"] == "user"


def test_llm_provider_routes_to_bedrock(monkeypatch):
    monkeypatch.setattr(llm_provider.settings, "llm_provider", "bedrock")
    monkeypatch.setattr(llm_provider.settings, "llm_fallback_provider", "mistral")
    monkeypatch.setattr(llm_provider.settings, "llm_fallback_enabled", "1")
    monkeypatch.setattr(llm_provider.settings, "bedrock_text_model_id", "test-model")
    monkeypatch.setattr(llm_provider.bedrock_client, "converse_with_trace", lambda *args, **kwargs: ("ok", {"provider": "bedrock", "model": "test-model"}))

    text, trace = llm_provider.chat_completion_with_trace("hello")

    assert text == "ok"
    assert trace["provider"] == "bedrock"
    assert trace["fallback"] is False


def test_agentcore_invoke_parses_json_response(monkeypatch):
    dummy_client = DummyAgentCoreClient()
    monkeypatch.setattr(agentcore_client.settings, "agentcore_runtime_arn", "arn:aws:bedrock-agentcore:us-east-1:123:runtime/test")
    monkeypatch.setattr(agentcore_client.settings, "agentcore_runtime_qualifier", "")
    monkeypatch.setattr(agentcore_client.settings, "agentcore_account_id", "")
    monkeypatch.setattr(agentcore_client.settings, "agentcore_content_type", "application/json")
    monkeypatch.setattr(agentcore_client.settings, "agentcore_accept", "application/json")
    monkeypatch.setattr(agentcore_client, "_client", lambda: dummy_client)

    payload = agentcore_client.invoke_agent_runtime(
        payload={"message": "hello"},
        session_id="REQ-123",
        runtime_user_id="E10231",
        trace_id="REQ-123",
    )

    assert payload["status"] == "completed"
    assert payload["message"] == "agentcore response"
    assert payload["agent_runtime"]["provider"] == "agentcore"
    assert dummy_client.request["runtimeSessionId"] == "REQ-123"
    assert json.loads(dummy_client.request["payload"].decode())["message"] == "hello"


def test_agentcore_provider_falls_back_to_local_when_disabled(monkeypatch):
    monkeypatch.setattr(agentcore_provider.settings, "agent_runtime_provider", "local")

    assert agentcore_provider.invoke_chat_if_configured(
        message="hello",
        employee_id="E10231",
        confirm=False,
        request_id="REQ-1",
    ) is None


def test_preflight_accepts_bedrock_configuration(monkeypatch):
    fake_settings = SimpleNamespace(
        database_url_env="postgresql://user:secret@host/db",
        db_password="",
        llm_provider_normalized="bedrock",
        aws_region="us-east-1",
        bedrock_text_model_id="test-model",
        bedrock_configured=True,
        agent_runtime_provider_normalized="local",
        api_key_required=False,
        api_key="",
        kb_storage_root="data/knowledge_base/uploads",
        cors_origins=lambda: ["https://example.com"],
    )
    monkeypatch.setattr(preflight_service, "settings", fake_settings)

    result = preflight_service._check_configuration()

    assert result["status"] == "pass"
    assert result["details"]["llm_provider"] == "bedrock"
