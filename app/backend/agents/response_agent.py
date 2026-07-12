from __future__ import annotations

import re
from typing import Any

from app.backend.agents.prompts import build_response_prompt
from app.backend.llm.provider import active_model_name, active_provider_name, chat_completion_with_trace


EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")


def _extract_user_fields(state: dict) -> dict[str, str]:
    user = state.get("user") or {}
    return {
        "full_name": str(user.get("full_name") or "").strip(),
        "email": str(user.get("email") or state.get("user_email") or "").strip(),
        "employee_id": str(user.get("user_id") or state.get("employee_id") or "").strip(),
    }


def _build_fallback_response(state: dict, result: dict) -> str:
    user = _extract_user_fields(state)
    name = user["full_name"] or "there"
    email = user["email"] or "your registered email address"

    action_message = result.get("message") or "Your request has been completed."

    return (
        f"Dear {name},\n\n"
        f"{action_message}\n\n"
        f"Registered email: {email}\n\n"
        f"If you do not receive the expected message within a few minutes, check your spam folder or contact the IT Service Desk.\n\n"
        f"Thank you,\nIT Service Desk"
    )


def _enforce_email(text: str, email: str) -> tuple[str, bool]:
    """Ensures the final response visibly includes the user's real email."""
    if not email:
        return text, False

    if EMAIL_RE.search(text or "") and email.lower() in text.lower():
        return text, False

    cleaned = (text or "").rstrip()
    if not cleaned:
        cleaned = "Your request has been completed."

    if "Registered email:" not in cleaned:
        cleaned += f"\n\nRegistered email: {email}"

    return cleaned, True


def build_final_message(state: dict, result: dict) -> tuple[str, dict[str, Any]]:
    user = _extract_user_fields(state)

    payload = {
        "message": state.get("message"),
        "workflow": state.get("workflow"),
        "user": state.get("user"),
        "account": state.get("account"),
        "rule": state.get("rule"),
        "evidence": state.get("evidence"),
        "memory_context": state.get("memory_context", {}),
        "result": result,
        "required_email": user["email"],
    }

    llm_trace: dict[str, Any] = {
        "used": False,
        "provider": active_provider_name(),
        "model": active_model_name(),
        "prompt_type": "final_response",
        "temperature": 0.2,
        "status": "pending",
        "guardrails": {
            "email_required": True,
            "email_value_present": bool(user["email"]),
        },
    }

    try:
        raw_text, provider_trace = chat_completion_with_trace(build_response_prompt(payload), temperature=0.2)
        final_text = (raw_text or "").strip()

        if not final_text:
            final_text = _build_fallback_response(state, result)
            provider_trace = {**provider_trace, "fallback_reason": "empty_model_response"}

        final_text, email_enforced = _enforce_email(final_text, user["email"])

        llm_trace.update(
            {
                **provider_trace,
                "used": bool(provider_trace.get("used", provider_trace.get("provider") != "local")),
                "status": "success",
                "fallback": bool(provider_trace.get("fallback", False)),
                "email_enforced": email_enforced,
            }
        )
        return final_text, llm_trace

    except Exception as exc:
        final_text = _build_fallback_response(state, result)

        if user["email"]:
            final_text, email_enforced = _enforce_email(final_text, user["email"])
        else:
            email_enforced = False

        llm_trace.update(
            {
                "used": False,
                "status": "fallback",
                "fallback": True,
                "error": str(exc),
                "email_enforced": email_enforced,
            }
        )
        return final_text, llm_trace
