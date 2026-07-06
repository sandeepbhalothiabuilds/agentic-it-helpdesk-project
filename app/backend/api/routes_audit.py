from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.backend.db.models import AuditLog
from app.backend.db.session import get_db

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("")
def list_audit_logs(
    request_id: str | None = Query(default=None),
    stage: str | None = Query(default=None),
    status: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(AuditLog)

    if active_only:
        query = query.filter(AuditLog.is_active.is_(True))
    if request_id:
        query = query.filter(AuditLog.request_id.ilike(f"%{request_id.strip()}%"))
    if stage:
        query = query.filter(AuditLog.stage.ilike(f"%{stage.strip()}%"))
    if status:
        query = query.filter(AuditLog.status.ilike(f"%{status.strip()}%"))

    rows = query.order_by(AuditLog.created_at.desc()).limit(limit).all()

    return [
        {
            "audit_id": row.audit_id,
            "request_id": row.request_id,
            "stage": row.stage,
            "status": row.status,
            "message": row.message,
            "created_at": row.created_at,
            "created_by": row.created_by,
            "updated_at": row.updated_at,
            "updated_by": row.updated_by,
            "is_active": row.is_active,
        }
        for row in rows
    ]
