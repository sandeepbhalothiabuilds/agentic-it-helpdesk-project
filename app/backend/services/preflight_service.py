from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.config import settings, truthy

REQUIRED_TABLES = [
    "users",
    "iam_accounts",
    "runbook_rules",
    "action_requests",
    "audit_logs",
    "service_tickets",
    "document_chunks",
    "knowledge_documents",
    "workflow_sessions",
    "workflow_events",
    "retrieval_logs",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _check(name: str, status: str, message: str, *, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "ok": status == "pass",
        "message": message,
        "details": details or {},
    }


def _setting(name: str, default: Any = None) -> Any:
    return getattr(settings, name, default)


def _scalar(db: Session, sql: str, params: dict[str, Any] | None = None) -> Any:
    return db.execute(text(sql), params or {}).scalar()


def _check_database(db: Session) -> dict[str, Any]:
    try:
        value = _scalar(db, "SELECT 1")
        return _check("database_connection", "pass", "Database connection succeeded.", details={"probe": value})
    except Exception as exc:
        return _check("database_connection", "error", "Database connection failed.", details={"error": str(exc)})


def _check_required_tables(db: Session) -> dict[str, Any]:
    missing: list[str] = []
    checked: list[str] = []

    try:
        for table_name in REQUIRED_TABLES:
            exists = _scalar(
                db,
                """
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'case4'
                  AND table_name = :table_name
                """,
                {"table_name": table_name},
            )
            checked.append(table_name)
            if int(exists or 0) == 0:
                missing.append(table_name)
    except Exception as exc:
        return _check(
            "required_tables",
            "warn",
            "Could not inspect PostgreSQL information_schema. This is expected in SQLite fallback tests.",
            details={"error": str(exc), "required_tables": REQUIRED_TABLES},
        )

    if missing:
        return _check(
            "required_tables",
            "error",
            "One or more required case4 tables are missing.",
            details={"missing": missing, "checked": checked},
        )

    return _check("required_tables", "pass", "All required case4 tables are present.", details={"checked": checked})


def _llm_provider() -> str:
    return str(_setting("llm_provider_normalized", _setting("llm_provider", "mistral")) or "mistral").lower()


def _agent_runtime_provider() -> str:
    return str(_setting("agent_runtime_provider_normalized", _setting("agent_runtime_provider", "local")) or "local").lower()


def _check_configuration() -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    has_database = bool(_setting("database_url_env", "") or _setting("db_password", ""))
    if not has_database:
        errors.append("Set DATABASE_URL or DB_PASSWORD.")

    provider = _llm_provider()
    if provider == "bedrock":
        if not _setting("aws_region", ""):
            errors.append("Set AWS_REGION when LLM_PROVIDER=bedrock.")
        if not _setting("bedrock_text_model_id", ""):
            errors.append("Set BEDROCK_TEXT_MODEL_ID when LLM_PROVIDER=bedrock.")
    elif provider == "mistral":
        mistral_enabled = bool(_setting("mistral_enabled", not truthy(_setting("mistral_disable", "0"))))
        if mistral_enabled and not _setting("mistral_api_key", ""):
            warnings.append("MISTRAL_API_KEY is not set. The local fallback may be used.")
    elif provider == "local":
        warnings.append("LLM_PROVIDER=local is only recommended for development or smoke tests.")
    else:
        warnings.append(f"Unknown LLM_PROVIDER '{provider}'. The provider facade will fall back to Mistral/local behavior.")

    embedding_provider = str(_setting("embedding_provider_normalized", _setting("embedding_provider", "huggingface")) or "huggingface").lower()
    if embedding_provider == "bedrock":
        if not _setting("aws_region", ""):
            errors.append("Set AWS_REGION when EMBEDDING_PROVIDER=bedrock.")
        if not _setting("bedrock_embedding_model_id", ""):
            errors.append("Set BEDROCK_EMBEDDING_MODEL_ID when EMBEDDING_PROVIDER=bedrock.")

    retrieval_provider = str(_setting("retrieval_provider_normalized", _setting("retrieval_provider", "db")) or "db").lower()
    if retrieval_provider == "bedrock_kb":
        if not _setting("aws_region", ""):
            errors.append("Set AWS_REGION when RETRIEVAL_PROVIDER=bedrock_kb.")
        if not _setting("bedrock_knowledge_base_id", ""):
            errors.append("Set BEDROCK_KNOWLEDGE_BASE_ID when RETRIEVAL_PROVIDER=bedrock_kb.")

    storage_backend = str(_setting("kb_storage_backend_normalized", _setting("kb_storage_backend", "local")) or "local").lower()
    if storage_backend == "s3" and not _setting("kb_s3_bucket", ""):
        errors.append("Set KB_S3_BUCKET when KB_STORAGE_BACKEND=s3.")

    agent_provider = _agent_runtime_provider()
    if agent_provider == "agentcore" and not _setting("agentcore_runtime_arn", ""):
        if bool(_setting("agentcore_local_fallback_enabled", truthy(_setting("agentcore_fallback_to_local", "1"), default=True))):
            warnings.append("AGENT_RUNTIME_PROVIDER=agentcore but AGENTCORE_RUNTIME_ARN is missing; local fallback is enabled.")
        else:
            errors.append("Set AGENTCORE_RUNTIME_ARN when AGENT_RUNTIME_PROVIDER=agentcore.")

    memory_enabled = bool(_setting("agentcore_memory_is_enabled", truthy(_setting("agentcore_memory_enabled", "0"), default=False)))
    if memory_enabled and not _setting("agentcore_memory_id", ""):
        errors.append("Set AGENTCORE_MEMORY_ID when AGENTCORE_MEMORY_ENABLED=true.")

    gateway_enabled = bool(_setting("agentcore_gateway_is_enabled", truthy(_setting("agentcore_gateway_enabled", "0"), default=False)))
    if gateway_enabled and not _setting("agentcore_gateway_url", ""):
        if bool(_setting("agentcore_gateway_mock_fallback_enabled", truthy(_setting("agentcore_gateway_fallback_to_mock", "1"), default=True))):
            warnings.append("AGENTCORE_GATEWAY_ENABLED=true but AGENTCORE_GATEWAY_URL is missing; local mock fallback is enabled.")
        else:
            errors.append("Set AGENTCORE_GATEWAY_URL when AGENTCORE_GATEWAY_ENABLED=true.")

    identity_enabled = bool(_setting("agentcore_identity_is_enabled", truthy(_setting("agentcore_identity_enabled", "0"), default=False)))
    if identity_enabled and not (_setting("agentcore_gateway_bearer_token", "") or _setting("agentcore_gateway_api_key", "")):
        errors.append("Set AGENTCORE_GATEWAY_BEARER_TOKEN or AGENTCORE_GATEWAY_API_KEY when AGENTCORE_IDENTITY_ENABLED=true.")

    if _setting("api_key_required", False) and not _setting("api_key", ""):
        errors.append("REQUIRE_API_KEY is enabled but APP_API_KEY is empty.")

    observability_enabled = bool(_setting("observability_is_enabled", truthy(_setting("observability_enabled", "1"), default=True)))
    emf_enabled = bool(_setting("observability_emf_logging_enabled", truthy(_setting("observability_emf_enabled", "0"), default=False)))
    namespace = str(_setting("observability_namespace", "AgenticITServiceDesk") or "AgenticITServiceDesk").strip()
    if observability_enabled and not namespace:
        warnings.append("OBSERVABILITY_NAMESPACE is empty; CloudWatch metrics will use the default namespace.")
    if str(_setting("app_env", "local")).lower() in {"prod", "production", "aws"} and observability_enabled and not emf_enabled:
        warnings.append("OBSERVABILITY_EMF_ENABLED is disabled in an AWS-like environment; CloudWatch custom metrics will not be emitted.")

    cors_origins = []
    if hasattr(settings, "cors_origins"):
        try:
            cors_origins = settings.cors_origins()
        except Exception:
            cors_origins = []
    if not cors_origins:
        warnings.append("No CORS origins are configured.")

    if storage_backend == "local" and not _setting("kb_storage_root", ""):
        warnings.append("KB_STORAGE_ROOT is empty.")

    details = {
        "database_configured": has_database,
        "llm_provider": provider,
        "mistral_enabled": bool(_setting("mistral_enabled", not truthy(_setting("mistral_disable", "0")))),
        "mistral_key_set": bool(_setting("mistral_api_key", "")),
        "aws_region": _setting("aws_region", ""),
        "bedrock_text_model_id": _setting("bedrock_text_model_id", ""),
        "bedrock_configured": bool(_setting("bedrock_configured", False)),
        "embedding_provider": embedding_provider,
        "bedrock_embedding_model_id": _setting("bedrock_embedding_model_id", ""),
        "bedrock_embedding_configured": bool(_setting("bedrock_embedding_configured", False)),
        "retrieval_provider": retrieval_provider,
        "bedrock_knowledge_base_id": _setting("bedrock_knowledge_base_id", ""),
        "bedrock_kb_configured": bool(_setting("bedrock_kb_configured", False)),
        "kb_storage_backend": storage_backend,
        "kb_s3_bucket_set": bool(_setting("kb_s3_bucket", "")),
        "kb_s3_prefix": _setting("kb_s3_prefix", "knowledge-base/uploads"),
        "agent_runtime_provider": agent_provider,
        "agentcore_runtime_arn_set": bool(_setting("agentcore_runtime_arn", "")),
        "agentcore_fallback_to_local": bool(_setting("agentcore_local_fallback_enabled", truthy(_setting("agentcore_fallback_to_local", "1"), default=True))),
        "agentcore_memory_enabled": memory_enabled,
        "agentcore_memory_id_set": bool(_setting("agentcore_memory_id", "")),
        "agentcore_memory_write_events": bool(_setting("agentcore_memory_write_enabled", truthy(_setting("agentcore_memory_write_events", "1"), default=True))),
        "agentcore_gateway_enabled": gateway_enabled,
        "agentcore_gateway_url_set": bool(_setting("agentcore_gateway_url", "")),
        "agentcore_gateway_fallback_to_mock": bool(_setting("agentcore_gateway_mock_fallback_enabled", truthy(_setting("agentcore_gateway_fallback_to_mock", "1"), default=True))),
        "agentcore_identity_enabled": identity_enabled,
        "agentcore_identity_configured": bool(_setting("agentcore_gateway_bearer_token", "") or _setting("agentcore_gateway_api_key", "")),
        "api_key_required": bool(_setting("api_key_required", False)),
        "api_key_configured": bool(_setting("api_key", "")),
        "observability_enabled": bool(_setting("observability_is_enabled", truthy(_setting("observability_enabled", "1"), default=True))),
        "observability_emf_enabled": bool(_setting("observability_emf_logging_enabled", truthy(_setting("observability_emf_enabled", "0"), default=False))),
        "observability_namespace": _setting("observability_namespace", "AgenticITServiceDesk"),
        "observability_redact_payloads": bool(_setting("observability_payload_redaction_enabled", truthy(_setting("observability_redact_payloads", "1"), default=True))),
        "cors_allowed_origins": cors_origins,
        "kb_storage_root": _setting("kb_storage_root", ""),
        "warnings": warnings,
        "errors": errors,
    }

    if errors:
        return _check("configuration", "error", "Required configuration is missing.", details=details)
    if warnings:
        return _check("configuration", "warn", "Configuration is usable with warnings.", details=details)
    return _check("configuration", "pass", "Configuration is ready.", details=details)


def _check_storage() -> dict[str, Any]:
    storage_backend = str(_setting("kb_storage_backend_normalized", _setting("kb_storage_backend", "local")) or "local").lower()
    if storage_backend == "s3":
        bucket = str(_setting("kb_s3_bucket", "") or "").strip()
        if not bucket:
            return _check(
                "knowledge_storage",
                "error",
                "S3 knowledge-base storage is selected but KB_S3_BUCKET is empty.",
                details={"storage_backend": "s3", "bucket_set": False},
            )
        return _check(
            "knowledge_storage",
            "pass",
            "S3 knowledge-base storage is configured. IAM access is validated during upload/download.",
            details={
                "storage_backend": "s3",
                "bucket_set": True,
                "prefix": _setting("kb_s3_prefix", "knowledge-base/uploads"),
            },
        )

    root = Path(_setting("kb_storage_root", "data/knowledge_base/uploads"))
    try:
        root.mkdir(parents=True, exist_ok=True)
        writable_probe = root / ".write_probe"
        writable_probe.write_text("ok", encoding="utf-8")
        writable_probe.unlink(missing_ok=True)
        return _check("knowledge_storage", "pass", "Knowledge-base storage is writable.", details={"storage_backend": "local", "path": str(root)})
    except Exception as exc:
        return _check("knowledge_storage", "error", "Knowledge-base storage is not writable.", details={"storage_backend": "local", "path": str(root), "error": str(exc)})


def _check_knowledge_base_counts(db: Session) -> dict[str, Any]:
    try:
        document_count = int(_scalar(db, "SELECT COUNT(*) FROM case4.knowledge_documents") or 0)
        active_chunk_count = int(_scalar(db, "SELECT COUNT(*) FROM case4.document_chunks WHERE is_active IS TRUE") or 0)
    except Exception as exc:
        return _check(
            "knowledge_base_counts",
            "warn",
            "Could not read knowledge-base counts. Run schema and ingestion before production traffic.",
            details={"error": str(exc)},
        )

    if document_count == 0 or active_chunk_count == 0:
        return _check(
            "knowledge_base_counts",
            "warn",
            "Knowledge base is reachable but has no active indexed content.",
            details={"knowledge_documents": document_count, "active_chunks": active_chunk_count},
        )

    return _check(
        "knowledge_base_counts",
        "pass",
        "Knowledge base contains active indexed content.",
        details={"knowledge_documents": document_count, "active_chunks": active_chunk_count},
    )


def run_preflight_checks(db: Session) -> dict[str, Any]:
    checks = [
        _check_configuration(),
        _check_storage(),
        _check_database(db),
        _check_required_tables(db),
        _check_knowledge_base_counts(db),
    ]

    summary = {
        "pass": sum(1 for item in checks if item["status"] == "pass"),
        "warn": sum(1 for item in checks if item["status"] == "warn"),
        "error": sum(1 for item in checks if item["status"] == "error"),
    }

    if summary["error"]:
        status = "error"
    elif summary["warn"]:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "ready": summary["error"] == 0,
        "generated_at": _now(),
        "summary": summary,
        "checks": checks,
    }
