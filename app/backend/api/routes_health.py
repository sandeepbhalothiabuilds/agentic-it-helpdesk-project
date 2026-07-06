from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.config import settings
from app.backend.db.session import get_db
from app.backend.services.admin_service import get_system_status
from app.backend.services.preflight_service import run_preflight_checks

router = APIRouter(tags=["health"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _health_base() -> dict[str, Any]:
    return {
        "service": settings.service_name,
        "environment": settings.app_env,
        "version": settings.app_version,
        "timestamp": _now(),
    }


@router.get("/health")
def health():
    return {
        "status": "ok",
        **_health_base(),
        "python_version": sys.version.split()[0],
    }


@router.get("/live")
@router.get("/health/live")
def liveness():
    return {
        "status": "ok",
        **_health_base(),
    }


@router.get("/version")
def version():
    return _health_base()


@router.get("/ready")
@router.get("/health/ready")
def readiness(response: Response, db: Session = Depends(get_db)):
    checks: dict[str, Any] = {
        "database": {"ok": False, "message": "not_checked"},
        "configuration": {
            "ok": len(settings.security_warnings) == 0,
            "warnings": settings.security_warnings,
        },
    }

    try:
        db.execute(text("SELECT 1")).scalar()
        checks["database"] = {"ok": True, "message": "Database reachable"}
    except Exception as exc:
        checks["database"] = {"ok": False, "message": str(exc)}

    preflight = run_preflight_checks(db)
    checks["preflight"] = {
        "ok": bool(preflight.get("ready")),
        "message": f"Preflight status: {preflight.get('status', 'unknown')}",
        "summary": preflight.get("summary", {}),
    }

    overall_ok = all(bool(item.get("ok")) for item in checks.values())
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if overall_ok else "not_ready",
        **_health_base(),
        "checks": checks,
        "preflight": preflight,
    }


@router.get("/health/config")
def health_config():
    return {
        "status": "ok",
        **_health_base(),
        "config": settings.public_config(),
    }


@router.get("/metrics")
def metrics(db: Session = Depends(get_db)):
    system = get_system_status(db)
    counts = system.get("counts", {}) if isinstance(system, dict) else {}
    return {
        "status": system.get("status", "unknown") if isinstance(system, dict) else "unknown",
        "timestamp": _now(),
        "metrics": {
            "workflow_sessions_total": counts.get("workflow_sessions", 0),
            "workflow_events_total": counts.get("workflow_events", 0),
            "retrieval_logs_total": counts.get("retrieval_logs", 0),
            "audit_logs_total": counts.get("audit_logs", 0),
            "service_tickets_total": counts.get("service_tickets", 0),
            "document_chunks_total": counts.get("document_chunks", 0),
            "knowledge_documents_total": counts.get("knowledge_documents", 0),
        },
    }
