from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agents.common import get_or_create_request_id, safe_log_workflow_event
from app.backend.tools.ticket_tool import create_incident_ticket


def create_ticket_for_request(db: Session, state: dict) -> dict:
    request_id = get_or_create_request_id(state)
    employee_id = state.get("employee_id", "UNKNOWN")

    if not state.get("confirm", False):
        return {
            "request_id": request_id,
            "ticket_created": False,
            "workflow_outcome": "skipped_no_confirmation",
        }

    ticket = create_incident_ticket(
        db=db,
        employee_id=employee_id,
        category=str(state.get("intent") or state.get("workflow") or "general_it_request"),
        summary=state.get("message", ""),
        priority="low",
        assigned_group="service-desk",
    )

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="ticket_agent",
        stage="ticket_creation",
        outcome="created",
        details={"ticket_id": ticket.get("ticket_id")},
    )

    return {
        "request_id": request_id,
        "ticket_created": True,
        "ticket": ticket,
        "workflow_outcome": "ticket_created",
    }