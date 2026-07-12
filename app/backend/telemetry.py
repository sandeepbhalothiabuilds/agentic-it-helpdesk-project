from __future__ import annotations

import hashlib
import logging
import random
import time
from contextlib import contextmanager
from typing import Any, Iterator

from app.backend.config import settings

logger = logging.getLogger("app.telemetry")

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "bearer",
    "content",
    "email",
    "message",
    "password",
    "payload",
    "prompt",
    "secret",
    "text",
    "token",
}


def _bool_setting(name: str, default: bool = False) -> bool:
    value = getattr(settings, name, None)
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "t", "yes", "y", "on", "enabled"}:
        return True
    if text in {"0", "false", "f", "no", "n", "off", "disabled", ""}:
        return False
    return default


def observability_enabled() -> bool:
    return bool(getattr(settings, "observability_is_enabled", _bool_setting("observability_enabled", True)))


def event_logging_enabled() -> bool:
    return bool(getattr(settings, "observability_event_logging_enabled", _bool_setting("observability_log_events", True)))


def emf_enabled() -> bool:
    return bool(getattr(settings, "observability_emf_logging_enabled", _bool_setting("observability_emf_enabled", False)))


def redact_payloads_enabled() -> bool:
    return bool(getattr(settings, "observability_payload_redaction_enabled", _bool_setting("observability_redact_payloads", True)))


def trace_prompts_enabled() -> bool:
    return bool(getattr(settings, "observability_prompt_tracing_enabled", _bool_setting("observability_trace_prompts", False)))


def _sampled() -> bool:
    try:
        rate = float(getattr(settings, "observability_sampling_rate", getattr(settings, "observability_sample_rate", 1.0)) or 1.0)
    except Exception:
        rate = 1.0
    rate = max(0.0, min(rate, 1.0))
    if rate >= 1.0:
        return True
    if rate <= 0.0:
        return False
    return random.random() <= rate


def _safe_key(key: Any) -> str:
    return str(key or "").strip().lower().replace("-", "_")


def _redacted_text(value: Any) -> str:
    text = "" if value is None else str(value)
    digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"<redacted len={len(text)} sha256={digest}>"


def sanitize(value: Any, *, include_payloads: bool | None = None) -> Any:
    """Return a telemetry-safe value for logs and CloudWatch metric properties."""
    include_payloads = trace_prompts_enabled() if include_payloads is None else include_payloads
    should_redact = redact_payloads_enabled() and not include_payloads

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key)
            normalized_key = _safe_key(key)
            if should_redact and any(sensitive in normalized_key for sensitive in SENSITIVE_KEYS):
                sanitized[key] = _redacted_text(raw_value)
            else:
                sanitized[key] = sanitize(raw_value, include_payloads=include_payloads)
        return sanitized

    if isinstance(value, list):
        return [sanitize(item, include_payloads=include_payloads) for item in value[:50]]

    if isinstance(value, tuple):
        return [sanitize(item, include_payloads=include_payloads) for item in value[:50]]

    if isinstance(value, (str, int, float, bool)) or value is None:
        if should_redact and isinstance(value, str) and len(value) > 1000:
            return _redacted_text(value)
        return value

    return str(value)


def _base_properties() -> dict[str, Any]:
    return {
        "service": getattr(settings, "service_name", "agentic-it-service-desk"),
        "environment": getattr(settings, "app_env", "local"),
        "version": getattr(settings, "service_version", "0.1.0"),
    }


def emit_event(
    event: str,
    *,
    request_id: str | None = None,
    operation: str | None = None,
    provider: str | None = None,
    status: str | None = None,
    duration_ms: float | None = None,
    properties: dict[str, Any] | None = None,
    level: int = logging.INFO,
) -> None:
    if not (observability_enabled() and event_logging_enabled() and _sampled()):
        return

    extra = {
        "event": event,
        "request_id": request_id,
        "operation": operation,
        "provider": provider,
        "status": status,
        "duration_ms": duration_ms,
        "telemetry": sanitize({**_base_properties(), **(properties or {})}),
    }
    logger.log(level, event, extra=extra)


def _metric_payload(
    metric_name: str,
    value: float,
    *,
    unit: str,
    dimensions: dict[str, Any] | None,
    properties: dict[str, Any] | None,
) -> dict[str, Any]:
    base_dimensions = {
        "Service": getattr(settings, "service_name", "agentic-it-service-desk"),
        "Environment": getattr(settings, "app_env", "local"),
    }
    for key, val in (dimensions or {}).items():
        if val is not None:
            base_dimensions[str(key)] = str(val)

    payload: dict[str, Any] = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [
                {
                    "Namespace": getattr(settings, "observability_namespace", "AgenticITServiceDesk"),
                    "Dimensions": [list(base_dimensions.keys())],
                    "Metrics": [{"Name": metric_name, "Unit": unit}],
                }
            ],
        },
        **base_dimensions,
        metric_name: float(value),
    }
    payload.update(sanitize(properties or {}))
    return payload


def emit_metric(
    metric_name: str,
    value: float = 1.0,
    *,
    unit: str = "Count",
    dimensions: dict[str, Any] | None = None,
    properties: dict[str, Any] | None = None,
) -> None:
    if not (observability_enabled() and emf_enabled() and _sampled()):
        return
    payload = _metric_payload(
        metric_name,
        value,
        unit=unit,
        dimensions=dimensions,
        properties=properties,
    )
    logger.info("telemetry_metric", extra={"emf_payload": payload})


def record_operation(
    operation: str,
    *,
    provider: str = "application",
    status: str = "success",
    duration_ms: float | None = None,
    request_id: str | None = None,
    properties: dict[str, Any] | None = None,
    error: str | None = None,
    extra_metrics: dict[str, tuple[float, str]] | None = None,
) -> dict[str, Any]:
    """Record a service operation as a JSON event and optional CloudWatch EMF metrics."""
    safe_status = status or "unknown"
    props = {
        **(properties or {}),
        "error": error,
    }
    props = {k: v for k, v in props.items() if v is not None}

    emit_event(
        "operation_completed",
        request_id=request_id,
        operation=operation,
        provider=provider,
        status=safe_status,
        duration_ms=duration_ms,
        properties=props,
        level=logging.ERROR if error or safe_status == "error" else logging.INFO,
    )

    dimensions = {"Operation": operation, "Provider": provider, "Status": safe_status}
    emit_metric("OperationCount", 1, dimensions=dimensions, properties=props)
    if duration_ms is not None:
        emit_metric("OperationLatencyMs", float(duration_ms), unit="Milliseconds", dimensions=dimensions, properties=props)
    if error or safe_status in {"error", "failed"}:
        emit_metric("OperationErrors", 1, dimensions=dimensions, properties=props)
    for metric_name, metric_spec in (extra_metrics or {}).items():
        metric_value, unit = metric_spec
        emit_metric(metric_name, float(metric_value), unit=unit, dimensions=dimensions, properties=props)

    return {
        "operation": operation,
        "provider": provider,
        "status": safe_status,
        "duration_ms": duration_ms,
        "request_id": request_id,
        "properties": sanitize(props),
    }


@contextmanager
def operation_timer(
    operation: str,
    *,
    provider: str = "application",
    request_id: str | None = None,
    properties: dict[str, Any] | None = None,
) -> Iterator[dict[str, Any]]:
    started = time.perf_counter()
    context: dict[str, Any] = {}
    try:
        yield context
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record_operation(
            operation,
            provider=provider,
            status="error",
            duration_ms=duration_ms,
            request_id=request_id,
            properties={**(properties or {}), **context},
            error=str(exc),
        )
        raise
    else:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record_operation(
            operation,
            provider=provider,
            status=str(context.get("status") or "success"),
            duration_ms=duration_ms,
            request_id=request_id,
            properties={**(properties or {}), **context},
        )


def telemetry_status() -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": observability_enabled(),
        "event_logging_enabled": event_logging_enabled(),
        "cloudwatch_emf_enabled": emf_enabled(),
        "namespace": getattr(settings, "observability_namespace", "AgenticITServiceDesk"),
        "redact_payloads": redact_payloads_enabled(),
        "trace_prompts": trace_prompts_enabled(),
        "sample_rate": getattr(settings, "observability_sampling_rate", getattr(settings, "observability_sample_rate", 1.0)),
        "message": "Telemetry is enabled." if observability_enabled() else "Telemetry is disabled.",
    }
