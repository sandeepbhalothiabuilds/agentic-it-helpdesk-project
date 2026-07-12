from __future__ import annotations

import json
import logging

from app.backend import telemetry
from app.backend.observability import JsonFormatter
from app.backend.services import admin_service, preflight_service


class DummyDB:
    pass


def test_telemetry_sanitizes_sensitive_payloads(monkeypatch):
    monkeypatch.setattr(telemetry.settings, "observability_enabled", "1")
    monkeypatch.setattr(telemetry.settings, "observability_redact_payloads", "1")
    monkeypatch.setattr(telemetry.settings, "observability_trace_prompts", "0")

    sanitized = telemetry.sanitize({"message": "unlock E10231", "safe_count": 3})

    assert sanitized["safe_count"] == 3
    assert str(sanitized["message"]).startswith("<redacted")
    assert "unlock E10231" not in str(sanitized["message"])


def test_emit_metric_adds_cloudwatch_emf_payload(monkeypatch, caplog):
    monkeypatch.setattr(telemetry.settings, "observability_enabled", "1")
    monkeypatch.setattr(telemetry.settings, "observability_emf_enabled", "1")
    monkeypatch.setattr(telemetry.settings, "observability_namespace", "AgenticITServiceDeskTest")
    monkeypatch.setattr(telemetry.settings, "service_name", "agentic-it-service-desk")
    monkeypatch.setattr(telemetry.settings, "app_env", "test")

    caplog.set_level(logging.INFO, logger="app.telemetry")
    telemetry.emit_metric(
        "OperationLatencyMs",
        42.0,
        unit="Milliseconds",
        dimensions={"Operation": "unit.test", "Provider": "pytest", "Status": "success"},
        properties={"request_id": "REQ-1"},
    )

    emf_records = [record for record in caplog.records if hasattr(record, "emf_payload")]
    assert emf_records
    payload = emf_records[-1].emf_payload
    assert payload["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "AgenticITServiceDeskTest"
    assert payload["OperationLatencyMs"] == 42.0
    assert payload["Operation"] == "unit.test"
    assert payload["Provider"] == "pytest"


def test_json_formatter_outputs_emf_as_top_level_json():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="app.telemetry",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="telemetry_metric",
        args=(),
        exc_info=None,
    )
    record.emf_payload = {"_aws": {"CloudWatchMetrics": []}, "OperationCount": 1}

    payload = json.loads(formatter.format(record))

    assert "_aws" in payload
    assert payload["OperationCount"] == 1
    assert "message" not in payload


def test_admin_status_includes_observability(monkeypatch):
    monkeypatch.setattr(admin_service, "_scalar", lambda db, sql, params=None: 1)
    monkeypatch.setattr(admin_service, "_probe_ollama", lambda: {"ok": True, "message": "ok"})
    monkeypatch.setattr(admin_service, "_safe_provider_status", lambda: {"active_provider": "mistral", "fallback_enabled": True, "mistral": {"ok": True}})
    monkeypatch.setattr(admin_service, "_safe_embedding_status", lambda: {"ok": True, "provider": "huggingface"})
    monkeypatch.setattr(admin_service, "_safe_bedrock_kb_status", lambda: {"ok": True, "provider": "bedrock_kb", "configured": False})
    monkeypatch.setattr(admin_service, "_safe_storage_status", lambda: {"ok": True, "provider": "local"})
    monkeypatch.setattr(admin_service, "_safe_agentcore_status", lambda: {"ok": True, "enabled": False, "fallback_to_local": True})
    monkeypatch.setattr(admin_service, "_safe_memory_status", lambda: {"ok": True, "enabled": False})
    monkeypatch.setattr(admin_service, "_safe_gateway_status", lambda: {"ok": True, "enabled": False, "fallback_to_mock": True})
    monkeypatch.setattr(admin_service, "_safe_identity_status", lambda: {"ok": True, "enabled": False})
    monkeypatch.setattr(admin_service, "_safe_preflight", lambda db: {"ready": True, "status": "ok", "summary": {"pass": 1, "warn": 0, "error": 0}, "checks": []})
    monkeypatch.setattr(admin_service, "_safe_telemetry_status", lambda: {"ok": True, "enabled": True, "cloudwatch_emf_enabled": True, "namespace": "AgenticITServiceDesk"})

    payload = admin_service.get_system_status(DummyDB())

    assert payload["health"]["observability"]["enabled"] is True
    assert payload["proof"]["cloudwatch_emf_enabled"] is True
    assert payload["proof"]["telemetry_namespace"] == "AgenticITServiceDesk"


def test_preflight_reports_observability_details(monkeypatch):
    monkeypatch.setattr(preflight_service.settings, "database_url_env", "postgresql://user:secret@host/db")
    monkeypatch.setattr(preflight_service.settings, "db_password", "")
    monkeypatch.setattr(preflight_service.settings, "llm_provider", "mistral")
    monkeypatch.setattr(preflight_service.settings, "mistral_api_key", "secret")
    monkeypatch.setattr(preflight_service.settings, "agent_runtime_provider", "local")
    monkeypatch.setattr(preflight_service.settings, "agentcore_memory_enabled", "0")
    monkeypatch.setattr(preflight_service.settings, "agentcore_gateway_enabled", "0")
    monkeypatch.setattr(preflight_service.settings, "agentcore_identity_enabled", "0")
    monkeypatch.setattr(preflight_service.settings, "require_api_key", "0")
    monkeypatch.setattr(preflight_service.settings, "kb_storage_backend", "local")
    monkeypatch.setattr(preflight_service.settings, "kb_storage_root", "data/knowledge_base/uploads")
    monkeypatch.setattr(preflight_service.settings, "observability_enabled", "1")
    monkeypatch.setattr(preflight_service.settings, "observability_emf_enabled", "0")
    monkeypatch.setattr(preflight_service.settings, "observability_namespace", "AgenticITServiceDesk")
    monkeypatch.setattr(preflight_service.settings, "app_env", "local")

    result = preflight_service._check_configuration()

    assert result["details"]["observability_enabled"] is True
    assert result["details"]["observability_namespace"] == "AgenticITServiceDesk"
