from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.backend.services.workflow_state_service import log_workflow_event

SUPPORTED_WORKFLOWS = {"password_reset", "account_unlock", "vpn_reenable"}
CLARIFY_WORKFLOW = "clarify"


def detect_workflow(message: str) -> str:
    text = (message or "").lower()
    if "password" in text:
        return "password_reset"
    if "unlock" in text or "locked" in text:
        return "account_unlock"
    if "vpn" in text or "remote access" in text:
        return "vpn_reenable"
    return CLARIFY_WORKFLOW


def normalize_label(label: str) -> str:
    text = (label or "").strip().lower()

    aliases = {
        "password reset": "password_reset",
        "reset password": "password_reset",
        "forgot password": "password_reset",
        "password_reset": "password_reset",
        "account locked": "account_unlock",
        "unlock account": "account_unlock",
        "account_unlock": "account_unlock",
        "vpn access": "vpn_reenable",
        "vpn issue": "vpn_reenable",
        "vpn_reenable": "vpn_reenable",
        "remote access": "vpn_reenable",
        "clarify": CLARIFY_WORKFLOW,
        "clarification": CLARIFY_WORKFLOW,
        "needs clarification": CLARIFY_WORKFLOW,
        "needs_clarification": CLARIFY_WORKFLOW,
        "access_request": CLARIFY_WORKFLOW,
        "general_it_request": CLARIFY_WORKFLOW,
    }

    return aliases.get(text, CLARIFY_WORKFLOW)


def workflow_rule_pattern(workflow: str) -> str:
    mapping = {
        "password_reset": "%password%",
        "account_unlock": "%unlock%",
        "vpn_reenable": "%vpn%",
    }
    return mapping.get(workflow, "%")


def get_or_create_request_id(state: dict[str, Any]) -> str:
    return state.get("request_id") or "PENDING"


def confirmation_required_from_rule(rule: dict[str, Any] | None) -> bool:
    """
    Convert the runbook confirmation flag into a safe boolean.

    The seed data stores this as text. Missing or unrecognized values are
    treated as requiring confirmation because the supported workflows are IAM
    or remote-access actions.
    """
    if not rule:
        return True

    raw = rule.get("confirmation_required", True)
    if isinstance(raw, bool):
        return raw

    text = str(raw).strip().lower()
    if text in {"no", "n", "false", "0", "not required", "none", "skip"}:
        return False
    if text in {"yes", "y", "true", "1", "required", "confirm", "confirmation required"}:
        return True

    return True


def safe_log_workflow_event(
    *,
    db: Session,
    request_id: str,
    employee_id: str,
    node_name: str,
    stage: str,
    outcome: str,
    details: dict | None = None,
) -> None:
    try:
        log_workflow_event(
            db=db,
            request_id=request_id,
            employee_id=employee_id,
            node_name=node_name,
            stage=stage,
            outcome=outcome,
            details=details or {},
        )
    except Exception as exc:
        print(
            f"[WORKFLOW_TRACE] Failed to log event for {node_name}/{stage}: {exc}",
            flush=True,
        )
