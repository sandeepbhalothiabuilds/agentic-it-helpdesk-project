from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agentcore.gateway import invoke_gateway_tool_if_configured
from app.backend.agents.common import (
    confirmation_required_from_rule,
    get_or_create_request_id,
    safe_log_workflow_event,
)
from app.backend.agents.response_agent import build_final_message
from app.backend.db.models import ActionRequest
from app.backend.services.audit_service import write_audit
from app.backend.tools.mock_iam import reenable_vpn, reset_password, unlock_account


def _can_execute(state: dict) -> bool:
    if state.get("confirm", False):
        return True
    return not confirmation_required_from_rule(state.get("rule"))


def _action_type_for_workflow(workflow: str) -> str:
    if workflow == "password_reset":
        return "Password Reset"
    if workflow == "account_unlock":
        return "Account Unlock"
    if workflow == "vpn_reenable":
        return "VPN Re-enable"
    return "Clarification"


def _execute_mock_action(workflow: str, employee_id: str) -> tuple[dict, str]:
    if workflow == "password_reset":
        return reset_password(employee_id), "Password Reset"
    if workflow == "account_unlock":
        return unlock_account(employee_id), "Account Unlock"
    if workflow == "vpn_reenable":
        return reenable_vpn(employee_id), "VPN Re-enable"
    return {"status": "needs_clarification", "message": "More details required"}, "Clarification"


def _tool_name_for_workflow(workflow: str) -> str | None:
    if workflow == "password_reset":
        return "reset_password"
    if workflow == "account_unlock":
        return "unlock_account"
    if workflow == "vpn_reenable":
        return "reenable_vpn"
    return None


def _execute_tool_action(workflow: str, employee_id: str, request_id: str, state: dict) -> tuple[dict, str]:
    action_type = _action_type_for_workflow(workflow)
    tool_name = _tool_name_for_workflow(workflow)
    if not tool_name:
        return _execute_mock_action(workflow, employee_id)

    gateway_result = invoke_gateway_tool_if_configured(
        tool_name=tool_name,
        tool_input={
            "employee_id": employee_id,
            "workflow": workflow,
            "request_id": request_id,
            "user": state.get("user") or {},
            "account": state.get("account") or {},
            "rule": state.get("rule") or {},
        },
        actor_id=employee_id,
        request_id=request_id,
    )
    if gateway_result is not None:
        gateway_result.setdefault("status", "Completed")
        gateway_result.setdefault("message", f"{action_type} completed for {employee_id}.")
        return gateway_result, action_type
    return _execute_mock_action(workflow, employee_id)


def execute_action(db: Session, state: dict) -> dict:
    employee_id = state.get("employee_id", "UNKNOWN")
    workflow = state.get("workflow", "clarify")
    request_id = get_or_create_request_id(state)

    if not state.get("user_found"):
        return {
            "request_id": request_id,
            "current_node": "execute_action",
            "status": "error",
            "response": {
                "status": "error",
                "message": "User context missing. Cannot execute action.",
            },
            "workflow_outcome": "error",
        }

    if not _can_execute(state):
        return {
            "request_id": request_id,
            "current_node": "execute_action",
            "status": "awaiting_confirmation",
            "needs_confirmation": True,
            "workflow_outcome": "skipped_no_confirmation",
            "response": {
                "status": "awaiting_confirmation",
                "message": "Confirmation is required before this action can be executed.",
                "needs_confirmation": True,
            },
        }

    if "user" not in state:
        return {
            "request_id": request_id,
            "current_node": "execute_action",
            "status": "error",
            "response": {
                "status": "error",
                "message": "User context missing. Cannot execute action.",
            },
            "workflow_outcome": "error",
        }

    action_row = (
        db.query(ActionRequest)
        .filter(ActionRequest.request_id == request_id)
        .first()
    )

    if not action_row:
        action_row = ActionRequest(
            request_id=request_id,
            user_id=state["user"]["user_id"],
            action_type=workflow,
            confirmation_status="confirmed" if state.get("confirm") else "not_required",
            execution_status="pending",
            evidence_ref="pending",
            outcome_notes="Auto-created before execution",
            created_by="agentic_app",
            updated_by="agentic_app",
        )
        db.add(action_row)
        db.commit()

    result, action_type = _execute_tool_action(workflow, employee_id, request_id, state)

    if action_type != "Clarification":
        action_row.action_type = action_type
        action_row.confirmation_status = "confirmed" if state.get("confirm") else "not_required"
        action_row.execution_status = result["status"]

        results = state.get("evidence", {}).get("results", [])
        action_row.evidence_ref = (
            results[0].get("source") if results and isinstance(results[0], dict) else "None"
        )
        action_row.outcome_notes = result["message"]
        action_row.updated_by = "agentic_app"
        db.commit()

        write_audit(db, request_id, "execute", result["status"], result["message"])

    final_message, llm_trace = build_final_message(state, result)

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="execute_action",
        stage="tool_execution",
        outcome=result.get("status", "completed"),
        details={
            "workflow": workflow,
            "action_type": action_type,
            "tool_execution": result.get("tool_execution"),
        },
    )
    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="response_agent",
        stage="llm_generation",
        outcome=llm_trace.get("status", "completed"),
        details=llm_trace,
    )

    response = {
        "workflow": workflow,
        "request_id": request_id,
        "user": state.get("user"),
        "account": state.get("account"),
        "rule": state.get("rule"),
        "evidence": state.get("evidence"),
        "retrieved_documents": state.get("retrieved_documents", []),
        "retrievals": state.get("retrievals", []),
        "documents": state.get("documents", []),
        "chunks": state.get("chunks", []),
        "memory_context": state.get("memory_context", {}),
        "result": result,
        "status": result.get("status", "completed"),
        "message": final_message,
        "llm_trace": llm_trace,
        "needs_confirmation": False,
    }

    return {
        "request_id": request_id,
        "current_node": "execute_action",
        "status": result.get("status", "completed"),
        "needs_confirmation": False,
        "result": result,
        "response": response,
        "evidence": state.get("evidence", {}),
        "retrieved_documents": state.get("retrieved_documents", []),
        "retrievals": state.get("retrievals", []),
        "documents": state.get("documents", []),
        "chunks": state.get("chunks", []),
        "memory_context": state.get("memory_context", {}),
        "llm_trace": llm_trace,
        "workflow_outcome": result.get("status", "completed"),
    }
