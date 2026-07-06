from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agents.common import (
    confirmation_required_from_rule,
    get_or_create_request_id,
    safe_log_workflow_event,
)
from app.backend.db.models import ActionRequest
from app.backend.services.audit_service import write_audit


def _approval_message(workflow: str) -> str:
    label = workflow.replace("_", " ").title()
    return f"Proposed action: {label}. Please confirm to continue."


def handle_confirmation(db: Session, state: dict) -> dict:
    employee_id = state.get("employee_id", "UNKNOWN")
    workflow = state.get("workflow", "clarify")
    request_id = get_or_create_request_id(state)

    if not state.get("user_found"):
        return {
            "request_id": request_id,
            "current_node": "confirm_action",
            "status": "error",
            "needs_confirmation": False,
            "approval_status": "blocked",
            "response": {
                "status": "error",
                "message": "No valid user context found. Cannot continue.",
                "needs_confirmation": False,
            },
            "workflow_outcome": "error",
        }

    if workflow == "clarify":
        return {
            "request_id": request_id,
            "current_node": "confirm_action",
            "status": "needs_clarification",
            "needs_confirmation": False,
            "approval_status": "not_required",
            "response": {
                "workflow": "clarify",
                "status": "needs_clarification",
                "message": "Please provide more details so I can safely choose the correct workflow.",
                "needs_confirmation": False,
            },
            "workflow_outcome": "needs_clarification",
        }

    confirmation_required = confirmation_required_from_rule(state.get("rule"))
    if not confirmation_required:
        write_audit(
            db,
            request_id=request_id,
            stage="confirm",
            status="not_required",
            message=f"Confirmation not required for workflow: {workflow}.",
        )
        safe_log_workflow_event(
            db=db,
            request_id=request_id,
            employee_id=employee_id,
            node_name="confirm_action",
            stage="approval_gate",
            outcome="not_required",
            details={"workflow": workflow, "confirmation_required": False},
        )
        return {
            "request_id": request_id,
            "current_node": "confirm_action",
            "needs_confirmation": False,
            "approval_status": "not_required",
            "workflow_outcome": "confirmation_not_required",
        }

    if not state.get("confirm", False):
        existing = (
            db.query(ActionRequest)
            .filter(ActionRequest.request_id == request_id)
            .first()
        )

        if not existing:
            action = ActionRequest(
                request_id=request_id,
                user_id=state["user"]["user_id"],
                action_type=workflow,
                confirmation_status="pending",
                execution_status="pending",
                evidence_ref="pending",
                outcome_notes="Awaiting user confirmation",
                created_by="agentic_app",
                updated_by="agentic_app",
            )
            db.add(action)
            db.commit()

        message = _approval_message(workflow)
        write_audit(
            db,
            request_id=request_id,
            stage="confirm",
            status="awaiting_confirmation",
            message=message,
        )

        safe_log_workflow_event(
            db=db,
            request_id=request_id,
            employee_id=employee_id,
            node_name="confirm_action",
            stage="approval_gate",
            outcome="waiting_for_confirmation",
            details={"workflow": workflow, "confirmation_required": True},
        )

        return {
            "request_id": request_id,
            "current_node": "confirm_action",
            "status": "awaiting_confirmation",
            "needs_confirmation": True,
            "approval_status": "awaiting_confirmation",
            "workflow_outcome": "waiting_for_confirmation",
            "response": {
                "workflow": workflow,
                "request_id": request_id,
                "status": "awaiting_confirmation",
                "message": message,
                "needs_confirmation": True,
                "evidence": state.get("evidence", {}),
            },
        }

    write_audit(
        db,
        request_id=request_id,
        stage="confirm",
        status="confirmed",
        message=f"User confirmed workflow: {workflow}.",
    )

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="confirm_action",
        stage="approval_gate",
        outcome="confirmed",
        details={"workflow": workflow, "confirmation_required": True},
    )

    return {
        "request_id": request_id,
        "current_node": "confirm_action",
        "needs_confirmation": False,
        "approval_status": "confirmed",
        "workflow_outcome": "confirmed",
    }
