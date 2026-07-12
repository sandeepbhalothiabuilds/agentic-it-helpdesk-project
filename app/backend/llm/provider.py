from __future__ import annotations

import logging
import time
from typing import Any

from app.backend.config import settings
from app.backend.llm import bedrock_client, mistral_client
from app.backend.telemetry import record_operation

logger = logging.getLogger(__name__)


SUPPORTED_PROVIDERS = {"bedrock", "mistral", "local"}


def active_provider_name() -> str:
    provider = settings.llm_provider_normalized
    return provider if provider in SUPPORTED_PROVIDERS else "mistral"


def active_model_name() -> str:
    provider = active_provider_name()
    if provider == "bedrock":
        return settings.bedrock_text_model_id or "bedrock:not_configured"
    if provider == "local":
        return "local-fallback"
    return settings.mistral_model


def _provider_order() -> list[str]:
    primary = active_provider_name()
    order = [primary]

    fallback = settings.llm_fallback_provider_normalized
    if settings.llm_can_fallback and fallback != "none" and fallback not in order:
        order.append(fallback)

    if settings.llm_can_fallback and "local" not in order:
        order.append("local")

    return [provider for provider in order if provider in SUPPORTED_PROVIDERS]


def _call_provider(provider: str, messages: Any, temperature: float, max_tokens: int | None, model: str | None) -> tuple[str, dict[str, Any]]:
    if provider == "bedrock":
        return bedrock_client.converse_with_trace(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model,
        )

    if provider == "mistral":
        started = time.perf_counter()
        text = mistral_client.chat_completion(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model=model or settings.mistral_model,
        )
        return text, {
            "provider": "mistral",
            "model": model or settings.mistral_model,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    started = time.perf_counter()
    return mistral_client._local_fallback_text(messages), {
        "provider": "local",
        "model": "local-fallback",
        "latency_ms": round((time.perf_counter() - started) * 1000, 2),
    }


def chat_completion_with_trace(
    messages: Any,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    model: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Call the configured LLM provider and return text plus a trace payload."""
    primary = active_provider_name()
    attempts: list[dict[str, Any]] = []

    for provider in _provider_order():
        try:
            text, provider_trace = _call_provider(provider, messages, temperature, max_tokens, model)
            trace = {
                "used": provider != "local",
                "provider": provider_trace.get("provider", provider),
                "primary_provider": primary,
                "model": provider_trace.get("model", active_model_name()),
                "status": "success" if text else "empty_response",
                "fallback": provider != primary,
                "attempts": attempts,
                **provider_trace,
            }
            if provider != primary:
                trace["fallback_reason"] = attempts[-1]["error"] if attempts else "primary_provider_not_used"
            record_operation(
                "llm.provider.chat_completion",
                provider=provider,
                status="success",
                duration_ms=trace.get("latency_ms"),
                properties={
                    "primary_provider": primary,
                    "fallback_used": provider != primary,
                    "model": trace.get("model"),
                    "attempt_count": len(attempts) + 1,
                },
            )
            return text, trace
        except Exception as exc:
            attempts.append({"provider": provider, "error": str(exc)})
            record_operation(
                "llm.provider.chat_completion",
                provider=provider,
                status="error",
                properties={"primary_provider": primary, "attempt_count": len(attempts)},
                error=str(exc),
            )
            logger.warning(
                "LLM provider attempt failed",
                extra={"event": "llm_provider_error", "provider": provider, "error": str(exc)},
            )
            if not settings.llm_can_fallback:
                raise

    # The loop always includes local fallback when fallback is enabled. This is only
    # reached if fallback was disabled and each provider failed.
    raise RuntimeError(f"All LLM providers failed: {attempts}")


def chat_completion(
    messages: Any,
    temperature: float = 0.2,
    max_tokens: int | None = None,
    model: str | None = None,
) -> str:
    text, _ = chat_completion_with_trace(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        model=model,
    )
    return text


def get_provider_status() -> dict[str, Any]:
    provider = active_provider_name()
    bedrock_status = bedrock_client.get_bedrock_status()
    return {
        "active_provider": provider,
        "active_model": active_model_name(),
        "fallback_provider": settings.llm_fallback_provider_normalized,
        "fallback_enabled": settings.llm_can_fallback,
        "bedrock": bedrock_status,
        "mistral": {
            "ok": bool(settings.mistral_enabled and settings.mistral_api_key),
            "enabled": settings.mistral_enabled,
            "model": settings.mistral_model,
            "api_key_set": bool(settings.mistral_api_key),
            "message": "Mistral is configured." if settings.mistral_api_key else "MISTRAL_API_KEY is not set.",
        },
    }
