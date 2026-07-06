from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scalar(db: Session, sql: str, params: dict | None = None) -> int:
    value = db.execute(text(sql), params or {}).scalar()
    return int(value or 0)


def _rows(db: Session, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


def _safe_scalar(
    db: Session,
    sql: str,
    *,
    default: int = 0,
    errors: list[str] | None = None,
    label: str | None = None,
) -> int:
    try:
        return _scalar(db, sql)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{label or 'query'}: {exc}")
        return default


def _safe_rows(
    db: Session,
    sql: str,
    *,
    errors: list[str] | None = None,
    label: str | None = None,
) -> list[dict[str, Any]]:
    try:
        return _rows(db, sql)
    except Exception as exc:
        if errors is not None:
            errors.append(f"{label or 'query'}: {exc}")
        return []


def get_dashboard_snapshot(db: Session) -> dict[str, Any]:
    errors: list[str] = []

    last_indexed_rows = _safe_rows(
        db,
        """
        SELECT MAX(updated_at) AS last_indexed
        FROM case4.knowledge_documents
        """,
        errors=errors,
        label="last_indexed",
    )
    last_indexed = last_indexed_rows[0].get("last_indexed") if last_indexed_rows else None

    summary = {
        "active_requests": _safe_scalar(
            db,
            """
            SELECT COUNT(*)
            FROM case4.workflow_sessions
            WHERE status IN ('in_progress', 'awaiting_confirmation')
            """,
            errors=errors,
            label="active_requests",
        ),
        "awaiting_confirmation": _safe_scalar(
            db,
            """
            SELECT COUNT(*)
            FROM case4.workflow_sessions
            WHERE needs_confirmation IS TRUE
              AND status = 'awaiting_confirmation'
            """,
            errors=errors,
            label="awaiting_confirmation",
        ),
        "completed_requests": _safe_scalar(
            db,
            """
            SELECT COUNT(*)
            FROM case4.workflow_sessions
            WHERE status = 'completed'
            """,
            errors=errors,
            label="completed_requests",
        ),
        "failed_requests": _safe_scalar(
            db,
            """
            SELECT COUNT(*)
            FROM case4.workflow_sessions
            WHERE status IN ('error', 'failed')
            """,
            errors=errors,
            label="failed_requests",
        ),
        "total_tickets": _safe_scalar(db, "SELECT COUNT(*) FROM case4.service_tickets", errors=errors, label="total_tickets"),
        "open_tickets": _safe_scalar(
            db,
            """
            SELECT COUNT(*)
            FROM case4.service_tickets
            WHERE LOWER(status) NOT IN ('closed', 'resolved', 'cancelled')
            """,
            errors=errors,
            label="open_tickets",
        ),
        "total_chunks": _safe_scalar(db, "SELECT COUNT(*) FROM case4.document_chunks", errors=errors, label="total_chunks"),
        "total_documents": _safe_scalar(
            db,
            "SELECT COUNT(DISTINCT source_document) FROM case4.document_chunks",
            errors=errors,
            label="total_documents",
        ),
        "total_retrieval_logs": _safe_scalar(db, "SELECT COUNT(*) FROM case4.retrieval_logs", errors=errors, label="total_retrieval_logs"),
        "total_workflow_events": _safe_scalar(db, "SELECT COUNT(*) FROM case4.workflow_events", errors=errors, label="total_workflow_events"),
        "total_audit_logs": _safe_scalar(db, "SELECT COUNT(*) FROM case4.audit_logs", errors=errors, label="total_audit_logs"),
        "active_workflows": _safe_scalar(
            db,
            """
            SELECT COUNT(DISTINCT workflow)
            FROM case4.document_chunks
            WHERE is_active IS TRUE
            """,
            errors=errors,
            label="active_workflows",
        ),
        "last_indexed": last_indexed,
    }

    recent_sessions = _safe_rows(
        db,
        """
        SELECT
            request_id,
            employee_id,
            intent,
            current_node,
            status,
            needs_confirmation,
            ticket_id,
            created_at,
            updated_at,
            EXTRACT(EPOCH FROM (updated_at - created_at)) AS duration_seconds
        FROM case4.workflow_sessions
        ORDER BY updated_at DESC
        LIMIT 10
        """,
        errors=errors,
        label="recent_sessions",
    )

    recent_tickets = _safe_rows(
        db,
        """
        SELECT
            t.ticket_id,
            u.employee_id,
            u.full_name,
            t.status,
            t.priority,
            t.category,
            t.summary,
            t.assigned_group,
            t.last_updated
        FROM case4.service_tickets t
        LEFT JOIN case4.users u
          ON u.user_id = t.user_id
        ORDER BY t.last_updated DESC
        LIMIT 10
        """,
        errors=errors,
        label="recent_tickets",
    )

    recent_audit = _safe_rows(
        db,
        """
        SELECT
            audit_id,
            request_id,
            stage,
            status,
            message,
            created_at,
            created_by
        FROM case4.audit_logs
        ORDER BY created_at DESC
        LIMIT 10
        """,
        errors=errors,
        label="recent_audit",
    )

    recent_events = _safe_rows(
        db,
        """
        SELECT
            event_id,
            request_id,
            employee_id,
            node_name,
            stage,
            outcome,
            created_at
        FROM case4.workflow_events
        ORDER BY created_at DESC
        LIMIT 20
        """,
        errors=errors,
        label="recent_events",
    )

    workflow_breakdown = _safe_rows(
        db,
        """
        SELECT
            COALESCE(intent, 'unknown') AS intent,
            status,
            COUNT(*) AS request_count,
            MAX(updated_at) AS last_updated
        FROM case4.workflow_sessions
        GROUP BY COALESCE(intent, 'unknown'), status
        ORDER BY request_count DESC, last_updated DESC
        LIMIT 12
        """,
        errors=errors,
        label="workflow_breakdown",
    )

    status = "ok" if not errors else "degraded"

    return {
        "status": status,
        "generated_at": _now(),
        "health": {
            "database": {
                "ok": len(errors) == 0,
                "message": "Dashboard queries completed" if not errors else "Some dashboard queries failed",
                "errors": errors,
            },
        },
        "summary": summary,
        "workflow_breakdown": workflow_breakdown,
        "recent_sessions": recent_sessions,
        "recent_requests": recent_sessions,
        "recent_tickets": recent_tickets,
        "recent_audit": recent_audit,
        "recent_events": recent_events,
        "warnings": errors,
    }
