from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urljoin

import requests

from app.backend.agentcore.identity import auth_headers, get_identity_status, identity_configured, identity_enabled
from app.backend.config import settings
from app.backend.telemetry import record_operation

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "t", "yes", "y", "on", "enabled"}
_FALSE = {"0", "false", "f", "no", "n", "off", "disabled", ""}


def _truthy_setting(value: Any, default: bool = False) -> bool:
    text = str(value if value is not None else "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def gateway_enabled() -> bool:
    return bool(getattr(settings, "agentcore_gateway_is_enabled", _truthy_setting(getattr(settings, "agentcore_gateway_enabled", "0"))))


def gateway_configured() -> bool:
    return gateway_enabled() and bool((getattr(settings, "agentcore_gateway_url", "") or "").strip())


def gateway_fallback_enabled() -> bool:
    if hasattr(settings, "agentcore_gateway_mock_fallback_enabled"):
        return bool(settings.agentcore_gateway_mock_fallback_enabled)
    return _truthy_setting(getattr(settings, "agentcore_gateway_fallback_to_mock", "1"), default=True)


def get_gateway_status() -> dict[str, Any]:
    enabled = gateway_enabled()
    configured = gateway_configured()
    identity_status = get_identity_status()
    status = {
        "ok": ((not enabled) or configured) and bool(identity_status.get("ok", True)),
        "enabled": enabled,
        "configured": configured,
        "url_set": bool(getattr(settings, "agentcore_gateway_url", "")),
        "tool_prefix": getattr(settings, "agentcore_gateway_tool_prefix", "tools"),
        "fallback_to_mock": gateway_fallback_enabled(),
        "identity": identity_status,
        "identity_enabled": identity_enabled(),
        "identity_configured": identity_configured(),
        "timeout_seconds": getattr(settings, "agentcore_gateway_timeout_seconds", 30),
        "message": "AgentCore Gateway is configured." if configured else "AgentCore Gateway is disabled or missing AGENTCORE_GATEWAY_URL.",
    }
    if enabled and not configured:
        status["ok"] = gateway_fallback_enabled()
    if enabled and identity_enabled() and not identity_configured():
        status["ok"] = False if not gateway_fallback_enabled() else status["ok"]
        status["message"] = "AgentCore Gateway is enabled but AgentCore Identity is not fully configured."
    return status


def _headers(*, actor_id: str | None = None, request_id: str | None = None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if actor_id:
        headers["X-AgentCore-Actor-Id"] = actor_id
    if request_id:
        headers["X-AgentCore-Request-Id"] = request_id
    headers.update(auth_headers(session_id=request_id))
    return headers


def _tool_url(tool_name: str) -> str:
    base = str(getattr(settings, "agentcore_gateway_url", "") or "").rstrip("/") + "/"
    prefix = str(getattr(settings, "agentcore_gateway_tool_prefix", "tools") or "tools").strip("/")
    path = f"{prefix}/{tool_name}" if prefix else tool_name
    return urljoin(base, path)


def _normalize_tool_response(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if "result" in payload and isinstance(payload["result"], dict):
        result = dict(payload["result"])
    elif "output" in payload and isinstance(payload["output"], dict):
        result = dict(payload["output"])
    else:
        result = dict(payload)

    status = result.get("status") or payload.get("status") or "Completed"
    message = result.get("message") or payload.get("message") or f"AgentCore Gateway tool '{tool_name}' completed."
    result["status"] = status
    result["message"] = message
    result.setdefault("tool_name", tool_name)
    result["tool_runtime"] = {
        "provider": "agentcore_gateway",
        "tool_name": tool_name,
        "gateway_status": payload.get("status"),
        "trace": payload.get("trace") or payload.get("metadata") or {},
    }
    return result


def invoke_gateway_tool(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    actor_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    if not gateway_configured():
        raise RuntimeError("AGENTCORE_GATEWAY_URL is required when AgentCore Gateway is enabled.")

    body = {
        "tool": tool_name,
        "input": tool_input,
        "actor_id": actor_id,
        "request_id": request_id,
        "source": "agentic-it-service-desk",
    }
    url = _tool_url(tool_name)
    timeout = int(getattr(settings, "agentcore_gateway_timeout_seconds", 30) or 30)
    logger.info("Invoking AgentCore Gateway tool", extra={"event": "agentcore_gateway_tool", "tool": tool_name, "request_id": request_id})
    started = time.perf_counter()
    try:
        response = requests.post(url, json=body, headers=_headers(actor_id=actor_id, request_id=request_id), timeout=timeout)
        response.raise_for_status()
        try:
            payload = response.json()
        except Exception:
            payload = {"status": "Completed", "message": response.text}
        if not isinstance(payload, dict):
            payload = {"status": "Completed", "message": str(payload)}
        result = _normalize_tool_response(tool_name, payload)
        record_operation(
            "agentcore.gateway.invoke_tool",
            provider="agentcore_gateway",
            status=str(result.get("status") or "completed").lower(),
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            request_id=request_id,
            properties={
                "tool_name": tool_name,
                "actor_id_set": bool(actor_id),
                "gateway_url_set": bool(getattr(settings, "agentcore_gateway_url", "")),
                "identity_enabled": identity_enabled(),
                "response_status_code": getattr(response, "status_code", None),
            },
        )
        return result
    except Exception as exc:
        record_operation(
            "agentcore.gateway.invoke_tool",
            provider="agentcore_gateway",
            status="error",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            request_id=request_id,
            properties={"tool_name": tool_name, "actor_id_set": bool(actor_id), "identity_enabled": identity_enabled()},
            error=str(exc),
        )
        raise


def invoke_gateway_tool_if_configured(
    *,
    tool_name: str,
    tool_input: dict[str, Any],
    actor_id: str | None = None,
    request_id: str | None = None,
) -> dict[str, Any] | None:
    if not gateway_enabled():
        return None
    if not gateway_configured():
        if gateway_fallback_enabled():
            logger.warning("AgentCore Gateway is enabled but not configured; falling back to local mock tool.")
            return None
        return {
            "status": "Failed",
            "message": "AgentCore Gateway is enabled but AGENTCORE_GATEWAY_URL is not configured.",
            "tool_runtime": get_gateway_status(),
        }
    if identity_enabled() and not identity_configured() and gateway_fallback_enabled():
        logger.warning("AgentCore Identity is enabled but not configured; falling back to local mock tool.")
        return None
    try:
        return invoke_gateway_tool(tool_name=tool_name, tool_input=tool_input, actor_id=actor_id, request_id=request_id)
    except Exception as exc:
        logger.exception("AgentCore Gateway invocation failed", extra={"event": "agentcore_gateway_error", "tool": tool_name, "request_id": request_id})
        if gateway_fallback_enabled():
            return None
        return {
            "status": "Failed",
            "message": f"AgentCore Gateway tool invocation failed: {exc}",
            "tool_runtime": {**get_gateway_status(), "error": str(exc), "tool_name": tool_name},
        }
