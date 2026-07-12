from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.agentcore.client import get_agentcore_status
from app.backend.agentcore.gateway import get_gateway_status, get_identity_status
from app.backend.agentcore.memory import get_memory_status
from app.backend.config import settings, truthy
from app.backend.llm.provider import get_provider_status
from app.backend.rag.bedrock_kb_service import get_bedrock_kb_status
from app.backend.rag.embedding_service import (
    EMBEDDING_PROVIDER,
    HF_MODEL,
    OLLAMA_MODEL,
    get_embedding_model_name,
    get_embedding_status,
)
from app.backend.services.preflight_service import run_preflight_checks
from app.backend.storage.s3_storage import get_storage_status
from app.backend.telemetry import telemetry_status


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scalar(db: Session, sql: str, params: dict | None = None) -> int:
    value = db.execute(text(sql), params or {}).scalar()
    return int(value or 0)


def _safe_scalar(db: Session, sql: str, params: dict | None = None) -> int:
    try:
        return _scalar(db, sql, params=params)
    except Exception:
        return 0


def _setting(name: str, default: Any = None) -> Any:
    return getattr(settings, name, default)


def _as_bool(value: Any, *, default: bool = False) -> bool:
    return truthy(value, default=default)


def _redact_database_url(value: Any) -> str:
    try:
        url = urlsplit(str(value))
    except Exception:
        return "hidden"
    if not url.scheme:
        return "hidden"
    netloc = url.hostname or ""
    if url.port:
        netloc = f"{netloc}:{url.port}"
    return urlunsplit((url.scheme, netloc, url.path or "", url.query, ""))


def _database_url_redacted() -> str:
    if hasattr(settings, "redacted_database_url"):
        try:
            return str(settings.redacted_database_url())
        except Exception:
            pass
    try:
        return _redact_database_url(settings.database_url)
    except Exception:
        return "not_configured"


def _normalize_llm_provider(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    if text_value in {"bedrock", "amazon_bedrock", "aws_bedrock"}:
        return "bedrock"
    if text_value in {"local", "fallback"}:
        return "local"
    if text_value in {"mistral", "mistral_ai"}:
        return "mistral"
    return text_value or "mistral"


def _configured_llm_provider(provider_status: dict[str, Any] | None = None) -> str:
    normalized = _setting("llm_provider_normalized", None)
    if normalized is not None:
        return _normalize_llm_provider(normalized)
    explicit = _setting("llm_provider", None)
    if explicit is not None:
        return _normalize_llm_provider(explicit)
    if _setting("mistral_model", None) is not None or _setting("mistral_api_key", None) is not None:
        return "mistral"
    return _normalize_llm_provider((provider_status or {}).get("active_provider"))


def _configured_llm_model(provider: str, provider_status: dict[str, Any] | None = None) -> str:
    if provider == "bedrock":
        return str(_setting("bedrock_text_model_id", "") or (provider_status or {}).get("active_model") or "bedrock:not_configured")
    if provider == "local":
        return "local-fallback"
    return str(_setting("mistral_model", "mistral-small-latest"))


def _normalize_agent_runtime_provider(value: Any) -> str:
    text_value = str(value or "").strip().lower()
    if text_value in {"agentcore", "bedrock_agentcore", "aws_agentcore"}:
        return "agentcore"
    return "local"


def _configured_agent_runtime_provider() -> str:
    normalized = _setting("agent_runtime_provider_normalized", None)
    if normalized is not None:
        return _normalize_agent_runtime_provider(normalized)
    return _normalize_agent_runtime_provider(_setting("agent_runtime_provider", "local"))


def _probe_ollama() -> dict[str, Any]:
    ollama_url = str(_setting("ollama_url", "http://localhost:11434")).rstrip("/")
    try:
        response = requests.get(f"{ollama_url}/api/tags", timeout=4)
        response.raise_for_status()
        models = response.json().get("models", [])
        return {
            "ok": True,
            "message": "Ollama is reachable",
            "base_url": ollama_url,
            "model_count": len(models),
            "models": models,
        }
    except Exception as exc:
        return {
            "ok": False,
            "message": str(exc),
            "base_url": ollama_url,
            "model_count": 0,
            "models": [],
        }


def _safe_provider_status() -> dict[str, Any]:
    try:
        return get_provider_status()
    except Exception as exc:
        provider = _configured_llm_provider({})
        fallback_enabled = _as_bool(_setting("llm_fallback_enabled", "1"), default=True)
        return {
            "active_provider": provider,
            "active_model": _configured_llm_model(provider, {}),
            "fallback_provider": _setting("llm_fallback_provider", "mistral"),
            "fallback_enabled": fallback_enabled,
            "bedrock": {
                "ok": False,
                "configured": False,
                "provider": "bedrock",
                "region": _setting("aws_region", "us-east-1"),
                "model_id": _setting("bedrock_text_model_id", ""),
                "message": str(exc),
                "validated": False,
                "boto3_available": False,
            },
            "mistral": {
                "ok": bool(_setting("mistral_enabled", _setting("mistral_disable", "0") != "1") and _setting("mistral_api_key", "")),
                "enabled": bool(_setting("mistral_enabled", _setting("mistral_disable", "0") != "1")),
                "model": _setting("mistral_model", "mistral-small-latest"),
                "api_key_set": bool(_setting("mistral_api_key", "")),
                "message": "Provider status fallback was used.",
            },
            "error": str(exc),
        }


def _fallback_status(name: str, exc: Exception, *, enabled_attr: str, configured_attr: str) -> dict[str, Any]:
    return {
        "ok": False,
        "enabled": bool(_setting(enabled_attr, False)),
        "configured": bool(_setting(configured_attr, False)),
        "message": str(exc),
        "name": name,
    }


def _safe_agentcore_status() -> dict[str, Any]:
    try:
        status = get_agentcore_status()
        if isinstance(status, dict):
            return status
    except Exception as exc:
        return {
            "ok": False,
            "enabled": _configured_agent_runtime_provider() == "agentcore",
            "configured": False,
            "runtime_arn_set": bool(_setting("agentcore_runtime_arn", "")),
            "fallback_to_local": _as_bool(_setting("agentcore_fallback_to_local", "1"), default=True),
            "message": str(exc),
        }
    return {
        "ok": False,
        "enabled": _configured_agent_runtime_provider() == "agentcore",
        "configured": False,
        "runtime_arn_set": bool(_setting("agentcore_runtime_arn", "")),
        "fallback_to_local": _as_bool(_setting("agentcore_fallback_to_local", "1"), default=True),
        "message": "AgentCore Runtime status was unavailable.",
    }


def _safe_memory_status() -> dict[str, Any]:
    enabled = bool(_setting("agentcore_memory_is_enabled", _as_bool(_setting("agentcore_memory_enabled", "0"))))
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "configured": False,
            "memory_id_set": bool(_setting("agentcore_memory_id", "")),
            "message": "AgentCore Memory is disabled.",
        }
    try:
        status = get_memory_status()
        if isinstance(status, dict):
            return status
    except Exception as exc:
        return _fallback_status("agentcore_memory", exc, enabled_attr="agentcore_memory_is_enabled", configured_attr="agentcore_memory_configured")
    return {
        "ok": False,
        "enabled": enabled,
        "configured": False,
        "message": "AgentCore Memory status was unavailable.",
    }


def _safe_gateway_status() -> dict[str, Any]:
    enabled = bool(_setting("agentcore_gateway_is_enabled", _as_bool(_setting("agentcore_gateway_enabled", "0"))))
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "configured": False,
            "fallback_to_mock": _as_bool(_setting("agentcore_gateway_fallback_to_mock", "1"), default=True),
            "message": "AgentCore Gateway is disabled.",
        }
    try:
        status = get_gateway_status()
        if isinstance(status, dict):
            return status
    except Exception as exc:
        return _fallback_status("agentcore_gateway", exc, enabled_attr="agentcore_gateway_is_enabled", configured_attr="agentcore_gateway_configured")
    return {
        "ok": False,
        "enabled": enabled,
        "configured": False,
        "fallback_to_mock": _as_bool(_setting("agentcore_gateway_fallback_to_mock", "1"), default=True),
        "message": "AgentCore Gateway status was unavailable.",
    }


def _safe_identity_status() -> dict[str, Any]:
    enabled = bool(_setting("agentcore_identity_is_enabled", _as_bool(_setting("agentcore_identity_enabled", "0"))))
    if not enabled:
        return {
            "ok": True,
            "enabled": False,
            "configured": False,
            "message": "AgentCore Identity is disabled.",
        }
    try:
        status = get_identity_status()
        if isinstance(status, dict):
            return status
    except Exception as exc:
        return _fallback_status("agentcore_identity", exc, enabled_attr="agentcore_identity_is_enabled", configured_attr="agentcore_identity_configured")
    return {
        "ok": False,
        "enabled": enabled,
        "configured": False,
        "message": "AgentCore Identity status was unavailable.",
    }


def _safe_embedding_status() -> dict[str, Any]:
    try:
        return get_embedding_status()
    except Exception as exc:
        return {
            "ok": False,
            "configured": False,
            "provider": str(_setting("embedding_provider", EMBEDDING_PROVIDER)),
            "model": "unknown",
            "message": str(exc),
        }


def _safe_bedrock_kb_status() -> dict[str, Any]:
    try:
        return get_bedrock_kb_status()
    except Exception as exc:
        return {
            "ok": False,
            "configured": False,
            "provider": "bedrock_kb",
            "message": str(exc),
        }


def _safe_storage_status() -> dict[str, Any]:
    try:
        return get_storage_status()
    except Exception as exc:
        return {
            "ok": False,
            "configured": False,
            "provider": str(_setting("kb_storage_backend", "local")),
            "message": str(exc),
        }


def _safe_telemetry_status() -> dict[str, Any]:
    try:
        return telemetry_status()
    except Exception as exc:
        return {
            "ok": False,
            "enabled": False,
            "message": str(exc),
        }


def _safe_preflight(db: Session) -> dict[str, Any]:
    try:
        preflight = run_preflight_checks(db)
        if isinstance(preflight, dict):
            return preflight
    except Exception as exc:
        return {
            "status": "degraded",
            "ready": False,
            "generated_at": _now(),
            "summary": {"pass": 0, "warn": 1, "error": 0},
            "checks": [
                {
                    "name": "preflight",
                    "status": "warn",
                    "ok": False,
                    "message": "Preflight checks could not be completed.",
                    "details": {"error": str(exc)},
                }
            ],
        }
    return {
        "status": "degraded",
        "ready": False,
        "generated_at": _now(),
        "summary": {"pass": 0, "warn": 1, "error": 0},
        "checks": [
            {
                "name": "preflight",
                "status": "warn",
                "ok": False,
                "message": "Preflight checks returned no payload.",
                "details": {},
            }
        ],
    }


def _public_config(provider_status: dict[str, Any] | None = None) -> dict[str, Any]:
    if hasattr(settings, "public_config"):
        try:
            config = settings.public_config()
        except Exception:
            config = {}
    else:
        config = {}

    provider_status = provider_status or _safe_provider_status()
    llm_provider = _configured_llm_provider(provider_status)
    agent_runtime_provider = _configured_agent_runtime_provider()
    fallback_enabled = provider_status.get("fallback_enabled")
    if fallback_enabled is None:
        fallback_enabled = _as_bool(_setting("llm_fallback_enabled", "1"), default=True)

    config.update(
        {
            "app_env": _setting("app_env", "local"),
            "service_name": _setting("service_name", "agentic-it-service-desk"),
            "service_version": _setting("service_version", "0.1.0"),
            "log_level": _setting("log_level", "INFO"),
            "llm_provider": llm_provider,
            "llm_model": _configured_llm_model(llm_provider, provider_status),
            "llm_fallback_provider": provider_status.get("fallback_provider") or _setting("llm_fallback_provider", "mistral"),
            "llm_fallback_enabled": bool(fallback_enabled),
            "mistral_model": _setting("mistral_model", "mistral-small-latest"),
            "mistral_enabled": bool(_setting("mistral_enabled", _setting("mistral_disable", "0") != "1")),
            "mistral_key_set": bool(_setting("mistral_api_key", "")),
            "aws_region": _setting("aws_region", "us-east-1"),
            "bedrock_text_model_id": _setting("bedrock_text_model_id", ""),
            "bedrock_configured": bool(_setting("bedrock_configured", False)),
            "bedrock_embedding_model_id": _setting("bedrock_embedding_model_id", ""),
            "bedrock_embedding_configured": bool(_setting("bedrock_embedding_configured", False)),
            "retrieval_provider": _setting("retrieval_provider_normalized", _setting("retrieval_provider", "db")),
            "retrieval_fallback_to_db": bool(_setting("retrieval_db_fallback_enabled", _as_bool(_setting("retrieval_fallback_to_db", "1"), default=True))),
            "bedrock_knowledge_base_id": _setting("bedrock_knowledge_base_id", ""),
            "bedrock_kb_configured": bool(_setting("bedrock_kb_configured", False)),
            "bedrock_kb_number_of_results": _setting("bedrock_kb_number_of_results", 5),
            "bedrock_kb_search_type": _setting("bedrock_kb_search_type", "HYBRID"),
            "agent_runtime_provider": agent_runtime_provider,
            "agentcore_enabled": agent_runtime_provider == "agentcore",
            "agentcore_configured": bool(_setting("agentcore_configured", False)),
            "agentcore_runtime_arn_set": bool(_setting("agentcore_runtime_arn", "")),
            "agentcore_runtime_qualifier": _setting("agentcore_runtime_qualifier", ""),
            "agentcore_memory_enabled": bool(_setting("agentcore_memory_is_enabled", _as_bool(_setting("agentcore_memory_enabled", "0")))),
            "agentcore_memory_configured": bool(_setting("agentcore_memory_configured", False)),
            "agentcore_memory_id_set": bool(_setting("agentcore_memory_id", "")),
            "agentcore_memory_write_events": bool(_setting("agentcore_memory_write_enabled", _as_bool(_setting("agentcore_memory_write_events", "1"), default=True))),
            "agentcore_memory_retrieve_enabled": bool(_setting("agentcore_memory_retrieval_enabled", _as_bool(_setting("agentcore_memory_retrieve_enabled", "0")))),
            "agentcore_memory_namespace": _setting("agentcore_memory_namespace", "/service-desk/{actorId}/"),
            "agentcore_memory_top_k": _setting("agentcore_memory_top_k", 3),
            "agentcore_gateway_enabled": bool(_setting("agentcore_gateway_is_enabled", _as_bool(_setting("agentcore_gateway_enabled", "0")))),
            "agentcore_gateway_configured": bool(_setting("agentcore_gateway_configured", False)),
            "agentcore_gateway_url_set": bool(_setting("agentcore_gateway_url", "")),
            "agentcore_gateway_fallback_to_mock": bool(_setting("agentcore_gateway_mock_fallback_enabled", _as_bool(_setting("agentcore_gateway_fallback_to_mock", "1"), default=True))),
            "agentcore_gateway_tool_prefix": _setting("agentcore_gateway_tool_prefix", ""),
            "agentcore_identity_enabled": bool(_setting("agentcore_identity_is_enabled", _as_bool(_setting("agentcore_identity_enabled", "0")))),
            "agentcore_identity_configured": bool(_setting("agentcore_gateway_bearer_token", "") or _setting("agentcore_gateway_api_key", "")),
            "embedding_provider": _setting("embedding_provider_normalized", EMBEDDING_PROVIDER),
            "embedding_model": get_embedding_model_name(),
            "embedding_fallback_provider": _setting("embedding_fallback_provider_normalized", _setting("embedding_fallback_provider", "huggingface")),
            "huggingface_model": HF_MODEL,
            "ollama_model": OLLAMA_MODEL,
            "ollama_url": _setting("ollama_url", "http://localhost:11434"),
            "database_url_redacted": _database_url_redacted(),
            "api_key_required": bool(_setting("api_key_required", False)),
            "api_key_configured": bool(_setting("api_key", "")),
            "kb_storage_backend": _setting("kb_storage_backend_normalized", _setting("kb_storage_backend", "local")),
            "kb_storage_root": _setting("kb_storage_root", "data/knowledge_base/uploads"),
            "kb_s3_bucket_set": bool(_setting("kb_s3_bucket", "")),
            "kb_s3_prefix": _setting("kb_s3_prefix", "knowledge-base/uploads"),
            "kb_s3_configured": bool(_setting("kb_s3_configured", False)),
            "request_timeout_seconds": _setting("request_timeout_seconds", 90),
        }
    )
    return config


def _llm_dependency_ok(*, llm_provider: str, provider_status: dict[str, Any], config: dict[str, Any]) -> bool:
    fallback_enabled = bool(config.get("llm_fallback_enabled"))
    if llm_provider == "bedrock":
        bedrock_health = provider_status.get("bedrock", {})
        return bool(isinstance(bedrock_health, dict) and bedrock_health.get("ok")) or fallback_enabled
    if llm_provider == "mistral":
        mistral_health = provider_status.get("mistral", {})
        mistral_ok = bool(isinstance(mistral_health, dict) and mistral_health.get("ok"))
        config_mistral_ok = bool(config.get("mistral_enabled") and config.get("mistral_key_set"))
        return mistral_ok or config_mistral_ok or fallback_enabled
    return True


def _agent_runtime_dependency_ok(*, agent_runtime_provider: str, agentcore_health: dict[str, Any]) -> bool:
    if agent_runtime_provider != "agentcore":
        return True
    fallback_enabled = bool(agentcore_health.get("fallback_to_local", True))
    return bool(agentcore_health.get("ok")) or fallback_enabled


def _memory_dependency_ok(memory_health: dict[str, Any]) -> bool:
    if not memory_health.get("enabled"):
        return True
    return bool(memory_health.get("ok"))


def _gateway_dependency_ok(gateway_health: dict[str, Any]) -> bool:
    if not gateway_health.get("enabled"):
        return True
    fallback_enabled = bool(gateway_health.get("fallback_to_mock", True))
    return bool(gateway_health.get("ok")) or fallback_enabled


def _identity_dependency_ok(identity_health: dict[str, Any]) -> bool:
    if not identity_health.get("enabled"):
        return True
    return bool(identity_health.get("ok"))


def get_system_status(db: Session) -> dict[str, Any]:
    database_ok = True
    db_error = None
    try:
        _ = _scalar(db, "SELECT 1")
    except Exception as exc:
        database_ok = False
        db_error = str(exc)

    ollama_health = _probe_ollama()
    ollama_ok = bool(ollama_health.get("ok"))
    provider_status = _safe_provider_status()
    bedrock_health = provider_status.get("bedrock", {}) if isinstance(provider_status.get("bedrock"), dict) else {}
    embedding_health = _safe_embedding_status()
    bedrock_kb_health = _safe_bedrock_kb_status()
    storage_health = _safe_storage_status()
    agentcore_health = _safe_agentcore_status()
    memory_health = _safe_memory_status()
    gateway_health = _safe_gateway_status()
    identity_health = _safe_identity_status()
    telemetry_health = _safe_telemetry_status()
    preflight = _safe_preflight(db)

    counts = {
        "workflow_sessions": _safe_scalar(db, "SELECT COUNT(*) FROM case4.workflow_sessions"),
        "workflow_events": _safe_scalar(db, "SELECT COUNT(*) FROM case4.workflow_events"),
        "retrieval_logs": _safe_scalar(db, "SELECT COUNT(*) FROM case4.retrieval_logs"),
        "audit_logs": _safe_scalar(db, "SELECT COUNT(*) FROM case4.audit_logs"),
        "service_tickets": _safe_scalar(db, "SELECT COUNT(*) FROM case4.service_tickets"),
        "document_chunks": _safe_scalar(db, "SELECT COUNT(*) FROM case4.document_chunks"),
        "documents": _safe_scalar(db, "SELECT COUNT(DISTINCT source_document) FROM case4.document_chunks"),
        "knowledge_documents": _safe_scalar(db, "SELECT COUNT(*) FROM case4.knowledge_documents"),
    }

    config = _public_config(provider_status)
    health = {
        "database": {
            "ok": database_ok,
            "message": "Database reachable" if database_ok else "Database error",
            "error": db_error,
        },
        "llm": provider_status,
        "bedrock": bedrock_health,
        "embedding": embedding_health,
        "bedrock_knowledge_base": bedrock_kb_health,
        "storage": storage_health,
        "agentcore": agentcore_health,
        "agentcore_memory": memory_health,
        "agentcore_gateway": gateway_health,
        "agentcore_identity": identity_health,
        "ollama": ollama_health,
        "observability": telemetry_health,
        "preflight": preflight,
    }

    embedding_provider = str(config.get("embedding_provider") or EMBEDDING_PROVIDER or "").lower()
    if embedding_provider == "ollama":
        embedding_dependency_ok = ollama_ok
    elif embedding_provider == "bedrock":
        embedding_dependency_ok = bool(embedding_health.get("ok"))
    else:
        embedding_dependency_ok = bool(embedding_health.get("ok", True))

    retrieval_provider = str(config.get("retrieval_provider") or "db").lower()
    retrieval_dependency_ok = True
    if retrieval_provider == "bedrock_kb":
        retrieval_dependency_ok = bool(bedrock_kb_health.get("ok")) or bool(config.get("retrieval_fallback_to_db"))

    storage_backend = str(config.get("kb_storage_backend") or "local").lower()
    storage_dependency_ok = True
    if storage_backend == "s3":
        storage_dependency_ok = bool(storage_health.get("ok"))

    llm_provider = str(config.get("llm_provider") or "mistral").lower()
    llm_dependency_ok = _llm_dependency_ok(llm_provider=llm_provider, provider_status=provider_status, config=config)
    agent_runtime_provider = str(config.get("agent_runtime_provider") or "local").lower()
    agentcore_dependency_ok = _agent_runtime_dependency_ok(agent_runtime_provider=agent_runtime_provider, agentcore_health=agentcore_health)
    memory_dependency_ok = _memory_dependency_ok(memory_health)
    gateway_dependency_ok = _gateway_dependency_ok(gateway_health)
    identity_dependency_ok = _identity_dependency_ok(identity_health)

    preflight_ready = bool(preflight.get("ready"))
    critical_ready = (
        database_ok
        and embedding_dependency_ok
        and retrieval_dependency_ok
        and storage_dependency_ok
        and llm_dependency_ok
        and agentcore_dependency_ok
        and memory_dependency_ok
        and gateway_dependency_ok
        and identity_dependency_ok
    )
    ready = critical_ready and preflight_ready

    if critical_ready:
        status = "ok"
    elif database_ok:
        status = "degraded"
    else:
        status = "error"

    return {
        "status": status,
        "ready": ready,
        "generated_at": _now(),
        "config": config,
        "health": health,
        "counts": counts,
        "preflight": preflight,
        "proof": {
            "database_ok": database_ok,
            "database_error": db_error,
            "ollama_ok": ollama_ok,
            "ollama_message": ollama_health.get("message"),
            "llm_provider": llm_provider,
            "llm_model": config.get("llm_model"),
            "llm_dependency_ok": llm_dependency_ok,
            "bedrock_ok": bool(bedrock_health.get("ok")),
            "bedrock_required": llm_provider == "bedrock",
            "embedding_provider": embedding_provider,
            "embedding_model": get_embedding_model_name(),
            "embedding_dependency_ok": embedding_dependency_ok,
            "retrieval_provider": retrieval_provider,
            "retrieval_dependency_ok": retrieval_dependency_ok,
            "storage_backend": storage_backend,
            "storage_dependency_ok": storage_dependency_ok,
            "storage_provider": storage_health.get("provider"),
            "storage_configured": bool(storage_health.get("configured")),
            "bedrock_kb_ok": bool(bedrock_kb_health.get("ok")),
            "bedrock_kb_required": retrieval_provider == "bedrock_kb",
            "agent_runtime_provider": agent_runtime_provider,
            "agent_runtime_dependency_ok": agentcore_dependency_ok,
            "agentcore_ok": bool(agentcore_health.get("ok")),
            "agentcore_required": agent_runtime_provider == "agentcore",
            "agentcore_memory_ok": bool(memory_health.get("ok")),
            "agentcore_memory_enabled": bool(memory_health.get("enabled")),
            "agentcore_memory_dependency_ok": memory_dependency_ok,
            "agentcore_gateway_ok": bool(gateway_health.get("ok")),
            "agentcore_gateway_enabled": bool(gateway_health.get("enabled")),
            "agentcore_gateway_dependency_ok": gateway_dependency_ok,
            "agentcore_identity_ok": bool(identity_health.get("ok")),
            "agentcore_identity_enabled": bool(identity_health.get("enabled")),
            "agentcore_identity_dependency_ok": identity_dependency_ok,
            "observability_enabled": bool(telemetry_health.get("enabled")),
            "cloudwatch_emf_enabled": bool(telemetry_health.get("cloudwatch_emf_enabled")),
            "telemetry_namespace": telemetry_health.get("namespace"),
            "critical_ready": critical_ready,
            "configuration_ready": preflight_ready,
            "api_key_required": bool(config.get("api_key_required")),
            "api_key_configured": bool(config.get("api_key_configured")),
        },
    }
