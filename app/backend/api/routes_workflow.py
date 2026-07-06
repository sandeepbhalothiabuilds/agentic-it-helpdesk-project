from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.services.workflow_state_service import (
    get_workflow_session,
    list_retrieval_logs,
    list_workflow_events,
    list_workflow_sessions,
)

router = APIRouter(prefix="/workflow", tags=["workflow"])


def _duration_seconds(start: Any, end: Any) -> float | None:
    if not start or not end:
        return None
    if isinstance(start, str):
        start = datetime.fromisoformat(start.replace("Z", "+00:00"))
    if isinstance(end, str):
        end = datetime.fromisoformat(end.replace("Z", "+00:00"))
    try:
        return round((end - start).total_seconds(), 3)
    except Exception:
        return None


@router.get("/sessions")
def workflow_sessions(
    employee_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return {
        "sessions": list_workflow_sessions(
            db,
            employee_id=employee_id,
            status=status,
            limit=limit,
        )
    }


@router.get("/history/{request_id}")
def workflow_history(
    request_id: str,
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
):
    session = get_workflow_session(db, request_id)
    events = list_workflow_events(db, request_id, limit=limit)
    retrieval_logs = list_retrieval_logs(db, request_id, limit=min(limit, 50))

    summary = {
        "request_id": request_id,
        "found": session is not None,
        "status": session.get("status") if isinstance(session, dict) else None,
        "intent": session.get("intent") if isinstance(session, dict) else None,
        "employee_id": session.get("employee_id") if isinstance(session, dict) else None,
        "event_count": len(events),
        "retrieval_count": len(retrieval_logs),
        "duration_seconds": _duration_seconds(
            session.get("created_at") if isinstance(session, dict) else None,
            session.get("updated_at") if isinstance(session, dict) else None,
        ),
    }

    return {
        "summary": summary,
        "session": session,
        "events": events,
        "retrieval_logs": retrieval_logs,
    }
