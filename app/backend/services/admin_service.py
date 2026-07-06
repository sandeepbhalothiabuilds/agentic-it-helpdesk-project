from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.config import settings
from app.backend.rag.embedding_service import (
    EMBEDDING_PROVIDER,
    HF_MODEL,
    OLLAMA_MODEL,
    get_embedding_model_name,
)
from app.backend.services.preflight_service import run_preflight_checks


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


def _setting(name: str, default: Any = None) -> Any:
    return getattr(settings, name, default)


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


def _safe_preflight(db: Session) -> dict[str, Any]:
    try:
        preflight = run_preflight_checks(db)
        return preflight if isinstance(preflight, dict) else {"status": "unknown", "ready": False}
    except Exception as exc:
        return {
            "status": "error",
            "ready": False,
            "summary": {"errors": 1, "warnings": 0},
            "checks": [
                {
                    "name": "preflight",
                    "status": "error",
                    "message": str(exc),
                }
            ],
        }


def _public_config() -> dict[str, Any]:
    if hasattr(settings, "public_config"):
        try:
            config = settings.public_config()
        except Exception:
            config = {}
    else:
        config = {}

    config.update(
        {
            "app_env": _setting("app_env", "local"),
            "service_name": _setting("service_name", "agentic-it-service-desk"),
            "service_version": _setting("service_version", "0.1.0"),
            "log_level": _setting("log_level", "INFO"),
            "mistral_model": _setting("mistral_model", "mistral-small-latest"),
            "mistral_enabled": bool(
                _setting("mistral_enabled", _setting("mistral_disable", "0") != "1")
            ),
            "mistral_key_set": bool(_setting("mistral_api_key", "")),
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_model": get_embedding_model_name(),
            "huggingface_model": HF_MODEL,
            "ollama_model": OLLAMA_MODEL,
            "ollama_url": _setting("ollama_url", "http://localhost:11434"),
            "database_url_redacted": _database_url_redacted(),
            "api_key_required": bool(_setting("api_key_required", False)),
            "api_key_configured": bool(_setting("api_key", "")),
            "kb_storage_root": _setting("kb_storage_root", "data/knowledge_base/uploads"),
            "request_timeout_seconds": _setting("request_timeout_seconds", 90),
        }
    )
    return config


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

    config = _public_config()
    health = {
        "database": {
            "ok": database_ok,
            "message": "Database reachable" if database_ok else "Database error",
            "error": db_error,
        },
        "ollama": ollama_health,
        "preflight": preflight,
    }

    provider = str(config.get("embedding_provider") or EMBEDDING_PROVIDER or "").strip().lower()
    embedding_dependency_ok = ollama_ok if provider == "ollama" else True
    configuration_ready = bool(preflight.get("ready"))

    # Keep these two concepts separate:
    # - status: whether the running service dependencies are healthy enough to answer requests.
    # - ready: whether the full production preflight is satisfied.
    #
    # This prevents optional/preflight checks from incorrectly marking the Admin status as
    # degraded during tests or local demos while still exposing readiness details for /ready.
    runtime_ok = database_ok and embedding_dependency_ok
    ready = runtime_ok and configuration_ready

    if runtime_ok:
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
            "ollama_ok": ollama_ok,
            "database_error": db_error,
            "ollama_message": ollama_health.get("message"),
            "embedding_provider": EMBEDDING_PROVIDER,
            "embedding_model": get_embedding_model_name(),
            "configuration_ready": configuration_ready,
            "runtime_ok": runtime_ok,
            "api_key_required": bool(config.get("api_key_required")),
            "api_key_configured": bool(config.get("api_key_configured")),
        },
    }
