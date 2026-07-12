from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agents.common import (
    detect_workflow,
    get_or_create_request_id,
    normalize_label,
    safe_log_workflow_event,
)
from app.backend.agents.prompts import build_classification_prompt
from app.backend.llm.provider import chat_completion


def classify_intent(db: Session, state: dict) -> dict:
    message = state.get("message", "")
    employee_id = state.get("employee_id", "UNKNOWN")
    request_id = get_or_create_request_id(state)

    print("ENTER classify", message, flush=True)

    prompt = build_classification_prompt(message)
    label = chat_completion(prompt, temperature=0)
    workflow = normalize_label(label)

    if workflow not in {"password_reset", "account_unlock", "vpn_reenable", "clarify"}:
        workflow = detect_workflow(message)

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="classify",
        stage="intent_classification",
        outcome="completed",
        details={"label": label, "workflow": workflow},
    )

    return {
        "request_id": request_id,
        "workflow": workflow,
        "intent": workflow,
        "current_node": "classify",
        "workflow_outcome": "completed",
    }