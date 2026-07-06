from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agents.common import get_or_create_request_id, safe_log_workflow_event

CLARIFICATION_MESSAGE = (
    "I need a little more detail before I can safely choose an IT workflow. "
    "Please describe the issue as a password reset, account unlock, or VPN access problem."
)


def build_clarification_response(db: Session, state: dict) -> dict:
    employee_id = state.get("employee_id", "UNKNOWN")
    request_id = get_or_create_request_id(state)

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="clarify",
        stage="clarification",
        outcome="needs_clarification",
        details={
            "message": state.get("message"),
            "workflow": state.get("workflow", "clarify"),
        },
    )

    return {
        "request_id": request_id,
        "workflow": "clarify",
        "intent": "clarify",
        "status": "needs_clarification",
        "current_node": "clarify",
        "workflow_outcome": "needs_clarification",
        "needs_confirmation": False,
        "response": {
            "status": "needs_clarification",
            "workflow": "clarify",
            "request_id": request_id,
            "message": CLARIFICATION_MESSAGE,
            "needs_confirmation": False,
        },
    }
