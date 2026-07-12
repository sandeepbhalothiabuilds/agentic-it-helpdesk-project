from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.backend.config import settings
from app.backend.llm.mistral_client import _local_fallback_text, _normalize_messages
from app.backend.telemetry import record_operation

logger = logging.getLogger(__name__)


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except Exception as exc:  # pragma: no cover - exercised by provider fallback tests
        raise RuntimeError("boto3 and botocore are required for Amazon Bedrock. Install boto3.") from exc
    return boto3, Config


def _session():
    boto3, _ = _load_boto3()
    profile = (settings.aws_profile or "").strip()
    if profile:
        return boto3.Session(profile_name=profile, region_name=settings.aws_region)
    return boto3.Session(region_name=settings.aws_region)


def _runtime_client():
    _, Config = _load_boto3()
    timeout = int(getattr(settings, "bedrock_request_timeout_seconds", 60) or 60)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return _session().client("bedrock-runtime", region_name=settings.aws_region, config=config)


def _control_client():
    _, Config = _load_boto3()
    timeout = int(getattr(settings, "bedrock_request_timeout_seconds", 60) or 60)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return _session().client("bedrock", region_name=settings.aws_region, config=config)


def _message_text(message: dict[str, Any]) -> str:
    content = message.get("content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def _to_bedrock_messages(messages: Any) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    normalized = _normalize_messages(messages)
    bedrock_messages: list[dict[str, Any]] = []
    system_prompts: list[dict[str, str]] = []

    for message in normalized:
        role = str(message.get("role") or "user").strip().lower()
        text = _message_text(message)
        if not text:
            continue

        if role == "system":
            system_prompts.append({"text": text})
            continue

        if role not in {"user", "assistant"}:
            role = "user"

        bedrock_messages.append(
            {
                "role": role,
                "content": [{"text": text}],
            }
        )

    if not bedrock_messages:
        bedrock_messages.append({"role": "user", "content": [{"text": ""}]})

    return bedrock_messages, system_prompts


def _extract_text(response: dict[str, Any]) -> str:
    content = (
        response.get("output", {})
        .get("message", {})
        .get("content", [])
    )
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and item.get("text"):
            parts.append(str(item["text"]))
    return "\n".join(parts).strip()


def _guardrail_config() -> dict[str, str] | None:
    identifier = (settings.bedrock_guardrail_identifier or "").strip()
    version = (settings.bedrock_guardrail_version or "").strip()
    if not identifier or not version:
        return None
    return {"guardrailIdentifier": identifier, "guardrailVersion": version}


def converse_with_trace(
    messages: Any,
    temperature: float | None = None,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Call Amazon Bedrock Converse and return generated text plus provider metadata."""
    started = time.perf_counter()
    model_id = (model or settings.bedrock_text_model_id or "").strip()
    telemetry_properties = {
        "model_id": model_id or "not_configured",
        "region": settings.aws_region,
        "guardrail_configured": bool(_guardrail_config()),
    }
    try:
        if not model_id:
            raise RuntimeError("BEDROCK_TEXT_MODEL_ID is required when LLM_PROVIDER=bedrock.")
        if not (settings.aws_region or "").strip():
            raise RuntimeError("AWS_REGION is required when LLM_PROVIDER=bedrock.")

        bedrock_messages, system_prompts = _to_bedrock_messages(messages)
        payload: dict[str, Any] = {
            "modelId": model_id,
            "messages": bedrock_messages,
            "inferenceConfig": {
                "temperature": float(settings.bedrock_temperature if temperature is None else temperature),
                "maxTokens": int(settings.bedrock_max_tokens if max_tokens is None else max_tokens),
            },
        }
        if system_prompts:
            payload["system"] = system_prompts

        guardrail = _guardrail_config()
        if guardrail:
            payload["guardrailConfig"] = guardrail

        client = _runtime_client()
        logger.info("Calling Amazon Bedrock Converse", extra={"event": "bedrock_converse", "model_id": model_id})
        response = client.converse(**payload)
        text = _extract_text(response)
        if not text:
            raise RuntimeError("Amazon Bedrock returned an empty response.")

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        usage = response.get("usage", {}) if isinstance(response.get("usage"), dict) else {}
        metrics = response.get("metrics", {}) if isinstance(response.get("metrics"), dict) else {}
        trace = {
            "provider": "bedrock",
            "model": model_id,
            "region": settings.aws_region,
            "latency_ms": duration_ms,
            "usage": usage,
            "metrics": metrics,
            "stop_reason": response.get("stopReason"),
            "guardrail_configured": bool(guardrail),
        }
        record_operation(
            "llm.bedrock.converse",
            provider="bedrock",
            status="success",
            duration_ms=duration_ms,
            properties={
                **telemetry_properties,
                "stop_reason": response.get("stopReason"),
                "input_tokens": usage.get("inputTokens"),
                "output_tokens": usage.get("outputTokens"),
                "total_tokens": usage.get("totalTokens"),
            },
            extra_metrics={
                "LLMInputTokens": (float(usage.get("inputTokens") or 0), "Count"),
                "LLMOutputTokens": (float(usage.get("outputTokens") or 0), "Count"),
                "LLMTotalTokens": (float(usage.get("totalTokens") or 0), "Count"),
            },
        )
        return text, trace
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record_operation(
            "llm.bedrock.converse",
            provider="bedrock",
            status="error",
            duration_ms=duration_ms,
            properties=telemetry_properties,
            error=str(exc),
        )
        raise


def chat_completion(
    messages: Any,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    model: str | None = None,
) -> str:
    """Text-only compatibility wrapper used by older call sites."""
    try:
        text, _ = converse_with_trace(messages, temperature=temperature, max_tokens=max_tokens, model=model)
        return text
    except Exception as exc:
        if settings.llm_can_fallback:
            logger.warning("Bedrock call failed; using local fallback", extra={"event": "bedrock_fallback", "error": str(exc)})
            return _local_fallback_text(messages)
        raise


def get_bedrock_status() -> dict[str, Any]:
    """Return configuration/readiness details without incurring model invocation cost by default."""
    configured = bool(settings.bedrock_configured)
    base = {
        "ok": configured,
        "configured": configured,
        "provider": "bedrock",
        "region": settings.aws_region,
        "model_id": settings.bedrock_text_model_id,
        "message": "Bedrock is configured." if configured else "Set AWS_REGION and BEDROCK_TEXT_MODEL_ID to use Bedrock.",
        "validated": False,
    }

    try:
        _load_boto3()
        base["boto3_available"] = True
    except Exception as exc:
        base.update({"ok": False, "boto3_available": False, "message": str(exc)})
        return base

    if not configured or not settings.bedrock_status_probe_enabled:
        return base

    try:
        client = _control_client()
        # This is a low-cost control-plane probe. Some IAM roles do not allow it,
        # so a failure here is surfaced but does not prevent runtime invocation when
        # the model permission exists.
        client.list_foundation_models(byOutputModality="TEXT")
        base.update({"ok": True, "validated": True, "message": "Bedrock control-plane probe succeeded."})
    except Exception as exc:
        base.update({"ok": False, "validated": True, "message": str(exc)})
    return base


def serialize_prompt_for_debug(messages: Any) -> str:
    try:
        return json.dumps(_normalize_messages(messages), ensure_ascii=False)
    except Exception:
        return str(messages)
