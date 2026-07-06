from sqlalchemy.orm import Session

from app.backend.services.ticket_service import create_ticket, update_ticket, get_ticket


def create_incident_ticket(
    db: Session,
    employee_id: str,
    category: str,
    summary: str,
    priority: str = "medium",
    assigned_group: str = "service-desk",
):
    ticket = create_ticket(
        db,
        employee_id=employee_id,
        category=category,
        summary=summary,
        priority=priority,
        assigned_group=assigned_group,
    )
    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "summary": ticket.summary,
        "assigned_group": ticket.assigned_group,
        "created_at": ticket.created_at,
    }


def change_ticket_status(db: Session, ticket_id: str, status: str):
    ticket = update_ticket(db, ticket_id=ticket_id, status=status)
    return {
        "ticket_id": ticket.ticket_id,
        "status": ticket.status,
        "last_updated": ticket.last_updated,
    }


def fetch_ticket(db: Session, ticket_id: str):
    ticket = get_ticket(db, ticket_id)
    if not ticket:
        return None

    return {
        "ticket_id": ticket.ticket_id,
        "user_id": ticket.user_id,
        "status": ticket.status,
        "priority": ticket.priority,
        "category": ticket.category,
        "summary": ticket.summary,
        "assigned_group": ticket.assigned_group,
        "created_at": ticket.created_at,
        "last_updated": ticket.last_updated,
    }