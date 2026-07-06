from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agents.common import (
    get_or_create_request_id,
    safe_log_workflow_event,
    workflow_rule_pattern,
)
from app.backend.db.models import IAMAccount, RunbookRule, User


def load_user_context(db: Session, state: dict) -> dict:
    employee_id = state.get("employee_id", "UNKNOWN")
    workflow = state.get("workflow", "clarify")
    request_id = get_or_create_request_id(state)

    print("ENTER load_context", employee_id, flush=True)

    user = db.query(User).filter(User.employee_id == employee_id).first()

    if not user:
        safe_log_workflow_event(
            db=db,
            request_id=request_id,
            employee_id=employee_id,
            node_name="load_context",
            stage="user_lookup",
            outcome="user_not_found",
            details={"employee_id": employee_id},
        )
        return {
            "request_id": request_id,
            "user_found": False,
            "current_node": "load_context",
            "response": {
                "status": "error",
                "message": f"No user found for employee_id={employee_id}",
            },
            "workflow_outcome": "user_not_found",
        }

    account = db.query(IAMAccount).filter(IAMAccount.user_id == user.user_id).first()

    rule = (
        db.query(RunbookRule)
        .filter(RunbookRule.workflow.ilike(workflow_rule_pattern(workflow)))
        .first()
    )

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="load_context",
        stage="user_lookup",
        outcome="completed",
        details={
            "user_id": user.user_id,
            "account_status": account.account_status if account else None,
            "workflow": workflow,
        },
    )

    return {
        "request_id": request_id,
        "user_found": True,
        "current_node": "load_context",
        "user": {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "manager": user.manager,
            "department": user.department,
            "email": getattr(user, "email", None),
        },
        "account": {
            "status": account.account_status if account else "unknown",
            "failed_login_count": account.failed_login_count if account else None,
        },
        "rule": {
            "confirmation_required": rule.confirmation_required if rule else "Yes",
        },
        "workflow_outcome": "completed",
    }