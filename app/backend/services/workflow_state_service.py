from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def upsert_workflow_session(
    db: Session,
    *,
    request_id: str,
    employee_id: str,
    message: str,
    intent: str | None = None,
    current_node: str = "start",
    status: str = "in_progress",
    needs_confirmation: bool = False,
    ticket_id: str | None = None,
    response_payload: dict | None = None,
    final_state: dict | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO case4.workflow_sessions (
                request_id,
                employee_id,
                message,
                intent,
                current_node,
                status,
                needs_confirmation,
                ticket_id,
                response_payload,
                final_state,
                created_at,
                updated_at
            )
            VALUES (
                :request_id,
                :employee_id,
                :message,
                :intent,
                :current_node,
                :status,
                :needs_confirmation,
                :ticket_id,
                CAST(:response_payload AS jsonb),
                CAST(:final_state AS jsonb),
                :created_at,
                :updated_at
            )
            ON CONFLICT (request_id)
            DO UPDATE SET
                employee_id = EXCLUDED.employee_id,
                message = EXCLUDED.message,
                intent = EXCLUDED.intent,
                current_node = EXCLUDED.current_node,
                status = EXCLUDED.status,
                needs_confirmation = EXCLUDED.needs_confirmation,
                ticket_id = EXCLUDED.ticket_id,
                response_payload = EXCLUDED.response_payload,
                final_state = EXCLUDED.final_state,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "request_id": request_id,
            "employee_id": employee_id,
            "message": message,
            "intent": intent,
            "current_node": current_node,
            "status": status,
            "needs_confirmation": needs_confirmation,
            "ticket_id": ticket_id,
            "response_payload": json.dumps(_jsonable(response_payload or {})),
            "final_state": json.dumps(_jsonable(final_state or {})),
            "created_at": _now(),
            "updated_at": _now(),
        },
    )
    db.commit()


def log_retrieval_event(
    db: Session,
    *,
    request_id: str,
    employee_id: str,
    query_text: str,
    document_name: str | None = None,
    chunk_id: str | None = None,
    score: float | None = None,
    retrieved_metadata: dict | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO case4.retrieval_logs (
                request_id,
                employee_id,
                query_text,
                document_name,
                chunk_id,
                score,
                retrieved_metadata,
                created_at
            )
            VALUES (
                :request_id,
                :employee_id,
                :query_text,
                :document_name,
                :chunk_id,
                :score,
                CAST(:retrieved_metadata AS jsonb),
                :created_at
            )
            """
        ),
        {
            "request_id": request_id,
            "employee_id": employee_id,
            "query_text": query_text,
            "document_name": document_name,
            "chunk_id": chunk_id,
            "score": score,
            "retrieved_metadata": json.dumps(_jsonable(retrieved_metadata or {})),
            "created_at": _now(),
        },
    )
    db.commit()


def log_workflow_event(
    db: Session,
    *,
    request_id: str,
    employee_id: str,
    node_name: str,
    stage: str,
    outcome: str,
    details: dict | None = None,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO case4.workflow_events (
                event_id,
                request_id,
                employee_id,
                node_name,
                stage,
                outcome,
                details,
                created_at,
                created_by,
                updated_at,
                updated_by,
                is_active
            )
            VALUES (
                :event_id,
                :request_id,
                :employee_id,
                :node_name,
                :stage,
                :outcome,
                CAST(:details AS jsonb),
                :created_at,
                :created_by,
                :updated_at,
                :updated_by,
                :is_active
            )
            """
        ),
        {
            "event_id": f"WFE-{uuid4().hex[:10].upper()}",
            "request_id": request_id,
            "employee_id": employee_id,
            "node_name": node_name,
            "stage": stage,
            "outcome": outcome,
            "details": json.dumps(_jsonable(details or {})),
            "created_at": _now(),
            "created_by": "agentic_app",
            "updated_at": _now(),
            "updated_by": "agentic_app",
            "is_active": True,
        },
    )
    db.commit()


def get_workflow_session(db: Session, request_id: str) -> dict | None:
    row = db.execute(
        text(
            """
            SELECT
                request_id,
                employee_id,
                message,
                intent,
                current_node,
                status,
                needs_confirmation,
                ticket_id,
                response_payload,
                final_state,
                created_at,
                updated_at
            FROM case4.workflow_sessions
            WHERE request_id = :request_id
            """
        ),
        {"request_id": request_id},
    ).mappings().first()

    if not row:
        return None

    return dict(row)


def list_retrieval_logs(db: Session, request_id: str, limit: int = 50) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT
                id,
                request_id,
                employee_id,
                query_text,
                document_name,
                chunk_id,
                score,
                retrieved_metadata,
                created_at
            FROM case4.retrieval_logs
            WHERE request_id = :request_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"request_id": request_id, "limit": limit},
    ).mappings().all()

    return [dict(row) for row in rows]


def list_workflow_events(db: Session, request_id: str, limit: int = 100) -> list[dict]:
    rows = db.execute(
        text(
            """
            SELECT
                event_id,
                request_id,
                employee_id,
                node_name,
                stage,
                outcome,
                details,
                created_at,
                created_by,
                updated_at,
                updated_by,
                is_active
            FROM case4.workflow_events
            WHERE request_id = :request_id
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        {"request_id": request_id, "limit": limit},
    ).mappings().all()

    return [dict(row) for row in rows]


def list_workflow_sessions(
    db: Session,
    *,
    employee_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
) -> list[dict]:
    filters = []
    params: dict[str, Any] = {"limit": limit}

    if employee_id:
        filters.append("LOWER(employee_id) LIKE LOWER(:employee_id)")
        params["employee_id"] = f"%{employee_id.strip()}%"

    if status:
        filters.append("LOWER(status) LIKE LOWER(:status)")
        params["status"] = f"%{status.strip()}%"

    where_sql = ""
    if filters:
        where_sql = "WHERE " + " AND ".join(filters)

    rows = db.execute(
        text(
            f"""
            SELECT
                request_id,
                employee_id,
                message,
                intent,
                current_node,
                status,
                needs_confirmation,
                ticket_id,
                created_at,
                updated_at,
                EXTRACT(EPOCH FROM (updated_at - created_at)) AS duration_seconds
            FROM case4.workflow_sessions
            {where_sql}
            ORDER BY updated_at DESC
            LIMIT :limit
            """
        ),
        params,
    ).mappings().all()

    return [dict(row) for row in rows]
