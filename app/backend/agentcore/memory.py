from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

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


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on AWS runtime packages
        raise RuntimeError("boto3 and botocore are required for Amazon Bedrock AgentCore Memory. Install boto3.") from exc
    return boto3, Config


def _session():
    boto3, _ = _load_boto3()
    profile = (getattr(settings, "aws_profile", "") or "").strip()
    region = getattr(settings, "aws_region", "us-east-1")
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def _data_client():
    _, Config = _load_boto3()
    timeout = int(getattr(settings, "agentcore_timeout_seconds", 90) or 90)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return _session().client("bedrock-agentcore", region_name=getattr(settings, "aws_region", "us-east-1"), config=config)


def memory_enabled() -> bool:
    return bool(getattr(settings, "agentcore_memory_is_enabled", _truthy_setting(getattr(settings, "agentcore_memory_enabled", "0"))))


def memory_configured() -> bool:
    return memory_enabled() and bool((getattr(settings, "agentcore_memory_id", "") or "").strip())


def memory_write_enabled() -> bool:
    if hasattr(settings, "agentcore_memory_write_enabled"):
        return bool(settings.agentcore_memory_write_enabled)
    return memory_enabled() and _truthy_setting(getattr(settings, "agentcore_memory_write_events", "1"), default=True)


def memory_retrieval_enabled() -> bool:
    if hasattr(settings, "agentcore_memory_retrieval_enabled"):
        return bool(settings.agentcore_memory_retrieval_enabled)
    return memory_configured() and _truthy_setting(getattr(settings, "agentcore_memory_retrieve_enabled", "0"), default=False)


def actor_id_for_employee(employee_id: str) -> str:
    prefix = str(getattr(settings, "agentcore_memory_actor_prefix", "employee") or "employee").strip() or "employee"
    cleaned = re.sub(r"[^A-Za-z0-9_.:-]+", "_", (employee_id or "unknown").strip())
    cleaned = cleaned.strip("._-:") or "unknown"
    return f"{prefix}_{cleaned}"


def _format_namespace(actor_id: str, session_id: str) -> str:
    template = str(
        getattr(settings, "agentcore_memory_namespace", "/summaries/{actorId}/{sessionId}/")
        or "/summaries/{actorId}/{sessionId}/"
    )
    return template.replace("{actorId}", actor_id).replace("{sessionId}", session_id)


def _metadata_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"stringValue": str(value).lower()}
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return {"numberValue": float(value)}
    if isinstance(value, datetime):
        return {"dateTimeValue": value}
    if isinstance(value, list):
        return {"stringListValue": [str(item) for item in value]}
    return {"stringValue": "" if value is None else str(value)}


def _metadata(values: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    raw = values or {}
    return {str(key): _metadata_value(value) for key, value in raw.items() if value is not None}


def _conversation_payload(*, user_message: str | None = None, assistant_message: str | None = None) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    if user_message:
        payload.append(
            {
                "conversational": {
                    "content": {"text": str(user_message)},
                    "role": "USER",
                }
            }
        )
    if assistant_message:
        payload.append(
            {
                "conversational": {
                    "content": {"text": str(assistant_message)},
                    "role": "ASSISTANT",
                }
            }
        )
    return payload


def _flatten_metadata(metadata: Any) -> dict[str, Any]:
    if not isinstance(metadata, dict):
        return {}

    flattened: dict[str, Any] = {}
    for key, value in metadata.items():
        if isinstance(value, dict):
            if "stringValue" in value:
                flattened[key] = value.get("stringValue")
            elif "stringListValue" in value:
                flattened[key] = value.get("stringListValue")
            elif "numberValue" in value:
                flattened[key] = value.get("numberValue")
            elif "dateTimeValue" in value:
                flattened[key] = value.get("dateTimeValue")
            else:
                flattened[key] = value
        else:
            flattened[key] = value
    return flattened


def _record_text(record: dict[str, Any]) -> str:
    content = record.get("content")
    if isinstance(content, dict):
        text = content.get("text")
        if text is not None:
            return str(text)
    for key in ("text", "summary", "value", "content"):
        if record.get(key) is not None:
            return str(record.get(key))
    return ""


def _normalize_record(record: dict[str, Any], index: int) -> dict[str, Any]:
    metadata = _flatten_metadata(record.get("metadata"))
    created_at = record.get("createdAt") or record.get("created_at")
    return {
        "memory_record_id": record.get("memoryRecordId") or record.get("id") or f"memory-{index}",
        "text": _record_text(record),
        "score": record.get("score"),
        "memory_strategy_id": record.get("memoryStrategyId") or record.get("strategyId"),
        "namespaces": record.get("namespaces") or [],
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        "metadata": metadata,
        "source": "agentcore_memory",
    }


def get_memory_status() -> dict[str, Any]:
    status = {
        "ok": (not memory_enabled()) or memory_configured(),
        "enabled": memory_enabled(),
        "configured": memory_configured(),
        "memory_id_set": bool(getattr(settings, "agentcore_memory_id", "")),
        "write_events": memory_write_enabled(),
        "retrieve_enabled": memory_retrieval_enabled(),
        "namespace": getattr(settings, "agentcore_memory_namespace", "/summaries/{actorId}/{sessionId}/"),
        "top_k": getattr(settings, "agentcore_memory_top_k", 3),
        "message": "AgentCore Memory is configured." if memory_configured() else "AgentCore Memory is disabled or missing AGENTCORE_MEMORY_ID.",
    }
    try:
        _load_boto3()
        status["boto3_available"] = True
    except Exception as exc:
        status["boto3_available"] = False
        if memory_enabled():
            status["ok"] = False
            status["message"] = str(exc)
    return status


def record_conversation_turn(
    *,
    employee_id: str,
    session_id: str,
    user_message: str | None = None,
    assistant_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write one user/assistant turn to AgentCore Memory when enabled.

    This is best-effort. Memory write failures are returned to the caller and
    logged as telemetry, but they should not fail the service-desk workflow.
    """
    if not memory_write_enabled():
        return {
            "ok": True,
            "status": "skipped",
            "skipped": True,
            "reason": "memory_disabled",
            "enabled": memory_enabled(),
        }

    if not memory_configured():
        return {
            "ok": False,
            "status": "skipped",
            "skipped": True,
            "reason": "memory_not_configured",
            **get_memory_status(),
        }

    payload = _conversation_payload(user_message=user_message, assistant_message=assistant_message)
    if not payload:
        return {"ok": True, "status": "skipped", "skipped": True, "reason": "empty_payload"}

    actor_id = actor_id_for_employee(employee_id)
    request: dict[str, Any] = {
        "memoryId": getattr(settings, "agentcore_memory_id", ""),
        "actorId": actor_id,
        "sessionId": session_id,
        "eventTimestamp": datetime.now(timezone.utc),
        "payload": payload,
        "metadata": _metadata({"employee_id": employee_id, "request_id": session_id, **(metadata or {})}),
    }
    extraction_mode = str(getattr(settings, "agentcore_memory_extraction_mode", "") or "").strip().upper()
    if extraction_mode:
        request["extractionMode"] = extraction_mode

    started = time.perf_counter()
    try:
        response = _data_client().create_event(**request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        event = response.get("event") if isinstance(response.get("event"), dict) else {}
        result = {
            "ok": True,
            "status": "written",
            "skipped": False,
            "memory_id": getattr(settings, "agentcore_memory_id", ""),
            "actor_id": actor_id,
            "session_id": session_id,
            "event_id": event.get("id") or response.get("eventId"),
            "response_metadata": response.get("ResponseMetadata", {}),
            "latency_ms": duration_ms,
        }
        record_operation(
            "agentcore.memory.create_event",
            provider="agentcore_memory",
            status="success",
            duration_ms=duration_ms,
            request_id=session_id,
            properties={
                "employee_id": employee_id,
                "actor_id": actor_id,
                "payload_item_count": len(payload),
                "memory_id_set": bool(getattr(settings, "agentcore_memory_id", "")),
            },
        )
        return result
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning(
            "AgentCore Memory write failed",
            extra={"event": "agentcore_memory_write_error", "session_id": session_id, "employee_id": employee_id},
            exc_info=True,
        )
        record_operation(
            "agentcore.memory.create_event",
            provider="agentcore_memory",
            status="error",
            duration_ms=duration_ms,
            request_id=session_id,
            properties={"employee_id": employee_id, "actor_id": actor_id, "memory_id_set": bool(getattr(settings, "agentcore_memory_id", ""))},
            error=str(exc),
        )
        return {
            "ok": False,
            "status": "error",
            "skipped": False,
            "memory_id": getattr(settings, "agentcore_memory_id", ""),
            "actor_id": actor_id,
            "session_id": session_id,
            "error": str(exc),
            "latency_ms": duration_ms,
        }


def create_conversation_event(
    *,
    employee_id: str,
    request_id: str | None = None,
    session_id: str | None = None,
    user_message: str | None = None,
    assistant_message: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return record_conversation_turn(
        employee_id=employee_id,
        session_id=session_id or request_id or "default-session",
        user_message=user_message,
        assistant_message=assistant_message,
        metadata=metadata,
    )


def retrieve_memory_context(*, employee_id: str, query: str, session_id: str | None = None, request_id: str | None = None) -> dict[str, Any]:
    """Retrieve relevant AgentCore Memory records using the documented API."""
    session_id = session_id or request_id or "default-session"
    if not memory_retrieval_enabled():
        return {"ok": True, "enabled": False, "records": [], "message": "Memory retrieval is disabled."}
    if not memory_configured():
        return {"ok": False, "enabled": True, "records": [], "message": "AgentCore Memory is not configured."}

    actor_id = actor_id_for_employee(employee_id)
    namespace = _format_namespace(actor_id, session_id)
    top_k = int(getattr(settings, "agentcore_memory_top_k", 3) or 3)
    search_criteria: dict[str, Any] = {
        "searchQuery": query or "service desk request context",
        "topK": top_k,
    }
    strategy_id = str(getattr(settings, "agentcore_memory_strategy_id", "") or "").strip()
    if strategy_id:
        search_criteria["memoryStrategyId"] = strategy_id

    request: dict[str, Any] = {
        "memoryId": getattr(settings, "agentcore_memory_id", ""),
        "namespace": namespace,
        "searchCriteria": search_criteria,
        "maxResults": top_k,
    }

    started = time.perf_counter()
    try:
        response = _data_client().retrieve_memory_records(**request)
        raw_records = response.get("memoryRecordSummaries") or response.get("memoryRecords") or response.get("records") or []
        records = [
            _normalize_record(record, index)
            for index, record in enumerate(raw_records, start=1)
            if isinstance(record, dict)
        ]
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record_operation(
            "agentcore.memory.retrieve",
            provider="agentcore_memory",
            status="success",
            duration_ms=duration_ms,
            request_id=session_id,
            properties={
                "employee_id": employee_id,
                "actor_id": actor_id,
                "namespace": namespace,
                "top_k": top_k,
                "record_count": len(records),
            },
            extra_metrics={"MemoryRecordCount": (float(len(records)), "Count")},
        )
        return {
            "ok": True,
            "enabled": True,
            "records": records,
            "record_count": len(records),
            "namespace": namespace,
            "actor_id": actor_id,
            "session_id": session_id,
            "memory_id": getattr(settings, "agentcore_memory_id", ""),
            "next_token": response.get("nextToken"),
            "latency_ms": duration_ms,
        }
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.warning(
            "AgentCore Memory retrieval failed",
            extra={"event": "agentcore_memory_retrieval_error", "session_id": session_id, "employee_id": employee_id},
            exc_info=True,
        )
        record_operation(
            "agentcore.memory.retrieve",
            provider="agentcore_memory",
            status="error",
            duration_ms=duration_ms,
            request_id=session_id,
            properties={"employee_id": employee_id, "actor_id": actor_id, "namespace": namespace, "top_k": top_k},
            error=str(exc),
        )
        return {
            "ok": False,
            "enabled": True,
            "records": [],
            "record_count": 0,
            "namespace": namespace,
            "actor_id": actor_id,
            "session_id": session_id,
            "error": str(exc),
            "latency_ms": duration_ms,
        }
