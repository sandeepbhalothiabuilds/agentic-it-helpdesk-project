from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.config import settings

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


def _check_configuration() -> dict[str, Any]:
    warnings: list[str] = []
    errors: list[str] = []

    has_database = bool(settings.database_url_env or settings.db_password)
    if not has_database:
        errors.append("Set DATABASE_URL or DB_PASSWORD.")

    if settings.mistral_enabled and not settings.mistral_api_key:
        warnings.append("MISTRAL_API_KEY is not set. The local fallback may be used.")

    if settings.api_key_required and not settings.api_key:
        errors.append("REQUIRE_API_KEY is enabled but APP_API_KEY is empty.")

    if not settings.cors_origins():
        warnings.append("No CORS origins are configured.")

    if not settings.kb_storage_root:
        warnings.append("KB_STORAGE_ROOT is empty.")

    details = {
        "database_configured": has_database,
        "mistral_enabled": settings.mistral_enabled,
        "mistral_key_set": bool(settings.mistral_api_key),
        "api_key_required": settings.api_key_required,
        "api_key_configured": bool(settings.api_key),
        "cors_allowed_origins": settings.cors_origins(),
        "kb_storage_root": settings.kb_storage_root,
        "warnings": warnings,
        "errors": errors,
    }

    if errors:
        return _check("configuration", "error", "Required configuration is missing.", details=details)
    if warnings:
        return _check("configuration", "warn", "Configuration is usable with warnings.", details=details)
    return _check("configuration", "pass", "Configuration is ready.", details=details)


def _check_storage() -> dict[str, Any]:
    root = Path(settings.kb_storage_root)
    try:
        root.mkdir(parents=True, exist_ok=True)
        writable_probe = root / ".write_probe"
        writable_probe.write_text("ok", encoding="utf-8")
        writable_probe.unlink(missing_ok=True)
        return _check("knowledge_storage", "pass", "Knowledge-base storage is writable.", details={"path": str(root)})
    except Exception as exc:
        return _check("knowledge_storage", "error", "Knowledge-base storage is not writable.", details={"path": str(root), "error": str(exc)})


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
