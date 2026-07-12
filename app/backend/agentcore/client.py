from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.backend.config import settings
from app.backend.telemetry import record_operation

logger = logging.getLogger(__name__)


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("boto3 and botocore are required for Amazon Bedrock AgentCore. Install boto3.") from exc
    return boto3, Config


def _session():
    boto3, _ = _load_boto3()
    profile = (settings.aws_profile or "").strip()
    if profile:
        return boto3.Session(profile_name=profile, region_name=settings.aws_region)
    return boto3.Session(region_name=settings.aws_region)


def _client():
    _, Config = _load_boto3()
    timeout = int(settings.agentcore_timeout_seconds or 90)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return _session().client("bedrock-agentcore", region_name=settings.aws_region, config=config)


def get_agentcore_status() -> dict[str, Any]:
    enabled = settings.agentcore_enabled
    configured = settings.agentcore_configured
    status = {
        "ok": (not enabled) or configured,
        "enabled": enabled,
        "configured": configured,
        "runtime_arn_set": bool(settings.agentcore_runtime_arn),
        "qualifier": settings.agentcore_runtime_qualifier,
        "account_id_set": bool(settings.agentcore_account_id),
        "fallback_to_local": settings.agentcore_local_fallback_enabled,
        "message": "AgentCore Runtime is configured." if configured else "AgentCore Runtime is disabled or missing AGENTCORE_RUNTIME_ARN.",
    }
    try:
        _load_boto3()
        status["boto3_available"] = True
    except Exception as exc:
        status.update({"ok": False if enabled else status["ok"], "boto3_available": False, "message": str(exc)})
    return status


def _read_streaming_body(body: Any) -> str:
    if body is None:
        return ""

    # Boto3 StreamingBody supports read(); event streams may support iteration or iter_lines().
    if hasattr(body, "read"):
        data = body.read()
        if isinstance(data, bytes):
            return data.decode("utf-8", errors="replace")
        return str(data)

    if hasattr(body, "iter_lines"):
        chunks: list[str] = []
        for line in body.iter_lines(chunk_size=10):
            if not line:
                continue
            text = line.decode("utf-8", errors="replace") if isinstance(line, bytes) else str(line)
            if text.startswith("data: "):
                text = text[6:]
            chunks.append(text)
        return "\n".join(chunks)

    chunks = []
    try:
        for chunk in body:
            if isinstance(chunk, bytes):
                chunks.append(chunk.decode("utf-8", errors="replace"))
            else:
                chunks.append(str(chunk))
    except TypeError:
        return str(body)
    return "".join(chunks)


def _parse_agentcore_response(raw_text: str) -> dict[str, Any]:
    cleaned = (raw_text or "").strip()
    if not cleaned:
        return {"status": "error", "message": "AgentCore returned an empty response."}

    # AgentCore samples may stream Server-Sent Event chunks. Keep only JSON-looking data
    # lines when the response is not a single JSON object.
    if "\ndata:" in cleaned or cleaned.startswith("data:"):
        lines: list[str] = []
        for line in cleaned.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                lines.append(line[5:].strip())
        if lines:
            cleaned = "\n".join(lines)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
        return {"status": "completed", "message": str(parsed), "agentcore_raw": parsed}
    except Exception:
        return {"status": "completed", "message": cleaned, "agentcore_raw_text": cleaned}


def invoke_agent_runtime(
    *,
    payload: dict[str, Any],
    session_id: str,
    runtime_user_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Invoke Amazon Bedrock AgentCore Runtime and normalize its response."""
    if not settings.agentcore_runtime_arn:
        raise RuntimeError("AGENTCORE_RUNTIME_ARN is required when AGENT_RUNTIME_PROVIDER=agentcore.")

    started = time.perf_counter()
    client = _client()
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    request: dict[str, Any] = {
        "agentRuntimeArn": settings.agentcore_runtime_arn,
        "runtimeSessionId": session_id,
        "payload": body,
        "contentType": settings.agentcore_content_type or "application/json",
        "accept": settings.agentcore_accept or "application/json",
    }
    if settings.agentcore_runtime_qualifier:
        request["qualifier"] = settings.agentcore_runtime_qualifier
    if settings.agentcore_account_id and ":" not in settings.agentcore_runtime_arn:
        request["accountId"] = settings.agentcore_account_id
    if runtime_user_id:
        request["runtimeUserId"] = runtime_user_id
    if trace_id:
        request["traceId"] = trace_id

    logger.info("Invoking AgentCore Runtime", extra={"event": "agentcore_invoke", "session_id": session_id})
    try:
        response = client.invoke_agent_runtime(**request)
        raw_text = _read_streaming_body(response.get("response"))
        parsed = _parse_agentcore_response(raw_text)
        parsed.setdefault("request_id", session_id)
        parsed.setdefault("status", "completed")
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        parsed["agent_runtime"] = {
            "provider": "agentcore",
            "runtime_session_id": response.get("runtimeSessionId") or session_id,
            "trace_id": response.get("traceId"),
            "status_code": response.get("statusCode"),
            "content_type": response.get("contentType"),
            "latency_ms": duration_ms,
        }
        record_operation(
            "agentcore.runtime.invoke",
            provider="agentcore",
            status=str(parsed.get("status") or "completed"),
            duration_ms=duration_ms,
            request_id=session_id,
            properties={
                "runtime_arn_set": bool(settings.agentcore_runtime_arn),
                "runtime_user_id_set": bool(runtime_user_id),
                "trace_id": response.get("traceId") or trace_id,
                "status_code": response.get("statusCode"),
                "response_length": len(raw_text or ""),
            },
        )
        return parsed
    except Exception as exc:
        record_operation(
            "agentcore.runtime.invoke",
            provider="agentcore",
            status="error",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            request_id=session_id,
            properties={"runtime_arn_set": bool(settings.agentcore_runtime_arn), "runtime_user_id_set": bool(runtime_user_id)},
            error=str(exc),
        )
        raise
