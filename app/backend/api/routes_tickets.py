from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.backend.db.models import ServiceTicket, User
from app.backend.db.session import get_db

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("")
def list_tickets(
    employee_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    category: str | None = Query(default=None),
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(ServiceTicket, User).outerjoin(User, ServiceTicket.user_id == User.user_id)

    if active_only:
        query = query.filter(ServiceTicket.is_active.is_(True))
    if employee_id:
        needle = employee_id.strip()
        query = query.filter(User.employee_id.ilike(f"%{needle}%"))
    if status:
        query = query.filter(ServiceTicket.status.ilike(f"%{status.strip()}%"))
    if priority:
        query = query.filter(ServiceTicket.priority.ilike(f"%{priority.strip()}%"))
    if category:
        query = query.filter(ServiceTicket.category.ilike(f"%{category.strip()}%"))

    rows = query.order_by(ServiceTicket.last_updated.desc()).limit(limit).all()

    results = []
    for ticket, user in rows:
        results.append(
            {
                "ticket_id": ticket.ticket_id,
                "user_id": ticket.user_id,
                "employee_id": user.employee_id if user else None,
                "full_name": user.full_name if user else None,
                "status": ticket.status,
                "priority": ticket.priority,
                "category": ticket.category,
                "summary": ticket.summary,
                "assigned_group": ticket.assigned_group,
                "created_at": ticket.created_at,
                "last_updated": ticket.last_updated,
                "created_by": ticket.created_by,
                "updated_by": ticket.updated_by,
                "is_active": ticket.is_active,
            }
        )

    return results
