from __future__ import annotations

import logging
from typing import Any

from app.backend.agentcore.client import get_agentcore_status, invoke_agent_runtime
from app.backend.config import settings

logger = logging.getLogger(__name__)


def should_use_agentcore() -> bool:
    return settings.agentcore_enabled and settings.agentcore_configured


def invoke_chat_if_configured(
    *,
    message: str,
    employee_id: str,
    confirm: bool,
    request_id: str,
    memory_context: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Return an AgentCore response when enabled, otherwise None for local workflow fallback."""
    if not settings.agentcore_enabled:
        return None

    if not settings.agentcore_configured:
        if settings.agentcore_local_fallback_enabled:
            logger.warning("AgentCore is enabled but not configured; falling back to local workflow.")
            return None
        return {
            "status": "failed",
            "message": "AgentCore Runtime is enabled but AGENTCORE_RUNTIME_ARN is not configured.",
            "request_id": request_id,
            "error": "agentcore_not_configured",
            "agent_runtime": get_agentcore_status(),
        }

    payload = {
        "message": message,
        "employee_id": employee_id,
        "confirm": confirm,
        "request_id": request_id,
        "source": "agentic-it-service-desk-fastapi",
        "memory_context": memory_context or {},
    }

    try:
        response = invoke_agent_runtime(
            payload=payload,
            session_id=request_id,
            runtime_user_id=employee_id,
            trace_id=request_id,
        )
        response.setdefault("request_id", request_id)
        response.setdefault("employee_id", employee_id)
        if memory_context:
            response.setdefault("memory_context", memory_context)
        return response
    except Exception as exc:
        logger.exception("AgentCore invocation failed", extra={"event": "agentcore_error", "request_id": request_id})
        if settings.agentcore_local_fallback_enabled:
            return None
        return {
            "status": "failed",
            "message": "AgentCore Runtime invocation failed.",
            "request_id": request_id,
            "employee_id": employee_id,
            "error": str(exc),
            "agent_runtime": get_agentcore_status(),
        }
