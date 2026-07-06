from uuid import uuid4
from sqlalchemy.orm import Session

from app.backend.db.models import AuditLog


def write_audit(db: Session, request_id: str, stage: str, status: str, message: str) -> None:
    row = AuditLog(
        audit_id=f"AU-{uuid4().hex[:8]}",
        request_id=request_id,
        stage=stage,
        status=status,
        message=message,
        created_by="agentic_app",
        updated_by="agentic_app",
    )
    db.add(row)
    db.commit()