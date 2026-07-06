from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session

from app.backend.db.models import ServiceTicket, User


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_ticket_id(prefix: str = "INC") -> str:
    """
    Generates a unique ticket id like:
    INC-20260703-4f2c1a8b
    """
    return f"{prefix}-{_now().strftime('%Y%m%d')}-{uuid4().hex[:8]}"


def get_user_by_employee_id(db: Session, employee_id: str) -> User | None:
    return db.query(User).filter(User.employee_id == employee_id).first()


def create_ticket(
    db: Session,
    *,
    employee_id: str,
    category: str,
    summary: str,
    priority: str = "medium",
    assigned_group: str = "service-desk",
    status: str = "open",
) -> ServiceTicket:
    """
    Creates a new row in case4.service_tickets using user_id from the Users table.
    """
    user = get_user_by_employee_id(db, employee_id)
    if user is None:
        raise ValueError(f"Unknown employee_id: {employee_id}")

    ticket = ServiceTicket(
        ticket_id=generate_ticket_id(),
        user_id=user.user_id,
        status=status,
        priority=priority,
        category=category,
        summary=summary,
        assigned_group=assigned_group,
        created_at=_now(),
        last_updated=_now(),
        created_by="system",
        updated_by="system",
        is_active=True,
    )

    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def update_ticket(
    db: Session,
    *,
    ticket_id: str,
    status: str | None = None,
    priority: str | None = None,
    assigned_group: str | None = None,
    summary: str | None = None,
    updated_by: str = "system",
) -> ServiceTicket:
    ticket = db.query(ServiceTicket).filter(ServiceTicket.ticket_id == ticket_id).first()
    if ticket is None:
        raise ValueError(f"Ticket not found: {ticket_id}")

    if status is not None:
        ticket.status = status
    if priority is not None:
        ticket.priority = priority
    if assigned_group is not None:
        ticket.assigned_group = assigned_group
    if summary is not None:
        ticket.summary = summary

    ticket.updated_by = updated_by
    ticket.last_updated = _now()

    db.commit()
    db.refresh(ticket)
    return ticket


def get_ticket(db: Session, ticket_id: str) -> ServiceTicket | None:
    return db.query(ServiceTicket).filter(ServiceTicket.ticket_id == ticket_id).first()


def list_tickets_for_employee(db: Session, employee_id: str, limit: int = 50):
    user = get_user_by_employee_id(db, employee_id)
    if user is None:
        return []

    return (
        db.query(ServiceTicket)
        .filter(ServiceTicket.user_id == user.user_id)
        .order_by(ServiceTicket.last_updated.desc())
        .limit(limit)
        .all()
    )