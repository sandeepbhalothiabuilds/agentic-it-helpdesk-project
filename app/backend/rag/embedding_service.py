from __future__ import annotations

import json
import logging
import os
import time
from functools import lru_cache
from typing import Any, List

import certifi
import requests

from app.backend.config import settings
from app.backend.telemetry import record_operation

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# Compatibility constants used by older services/tests. Runtime code should use the
# helper functions below so environment changes are reflected without editing code.
EMBEDDING_PROVIDER = settings.embedding_provider_normalized
EMBEDDING_FALLBACK_PROVIDER = settings.embedding_fallback_provider_normalized
HF_MODEL = settings.huggingface_model
OLLAMA_URL = settings.ollama_url
OLLAMA_MODEL = settings.ollama_model
OLLAMA_TIMEOUT = int(settings.ollama_timeout_seconds or 120)
BEDROCK_EMBEDDING_MODEL_ID = settings.bedrock_embedding_model_id


def _setup_hf_tls() -> None:
    """Make Hugging Face downloads use a trusted CA store."""
    try:
        import truststore  # type: ignore

        truststore.inject_into_ssl()
        logger.info("[EMBEDDINGS] Using OS trust store via truststore")
    except Exception as exc:
        logger.info("[EMBEDDINGS] truststore not available: %s", exc)

    os.environ.setdefault("REQUESTS_CA_BUNDLE", certifi.where())
    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    os.environ.setdefault("CURL_CA_BUNDLE", certifi.where())


_setup_hf_tls()


def _provider() -> str:
    return getattr(settings, "embedding_provider_normalized", settings.embedding_provider or EMBEDDING_PROVIDER).strip().lower()


def _fallback_provider() -> str:
    return getattr(settings, "embedding_fallback_provider_normalized", settings.embedding_fallback_provider or EMBEDDING_FALLBACK_PROVIDER).strip().lower()


def _hf_model_name() -> str:
    return str(getattr(settings, "huggingface_model", HF_MODEL) or HF_MODEL)


def _ollama_url() -> str:
    return str(getattr(settings, "ollama_url", OLLAMA_URL) or OLLAMA_URL)


def _ollama_model_name() -> str:
    return str(getattr(settings, "ollama_model", OLLAMA_MODEL) or OLLAMA_MODEL)


def _bedrock_embedding_model_id() -> str:
    return str(getattr(settings, "bedrock_embedding_model_id", BEDROCK_EMBEDDING_MODEL_ID) or BEDROCK_EMBEDDING_MODEL_ID).strip()


def _embed_ollama(text: str) -> list[float]:
    url = f"{_ollama_url().rstrip('/')}/api/embeddings"
    payload = {
        "model": _ollama_model_name(),
        "prompt": text,
    }

    response = requests.post(
        url,
        json=payload,
        timeout=int(getattr(settings, "ollama_timeout_seconds", OLLAMA_TIMEOUT) or OLLAMA_TIMEOUT),
    )
    response.raise_for_status()

    data = response.json()
    embedding = data.get("embedding", [])

    if not isinstance(embedding, list):
        raise ValueError("Ollama returned an invalid embedding payload")

    return [float(x) for x in embedding]


@lru_cache(maxsize=1)
def _load_hf_model():
    from sentence_transformers import SentenceTransformer

    model_name = _hf_model_name()
    logger.info("[EMBEDDINGS] Loading HuggingFace model: %s", model_name)
    return SentenceTransformer(model_name)


def _embed_huggingface(text: str) -> list[float]:
    model = _load_hf_model()
    vec = model.encode(text, normalize_embeddings=True)

    if hasattr(vec, "tolist"):
        return vec.tolist()

    return list(vec)


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except Exception as exc:  # pragma: no cover - deployment/environment dependent
        raise RuntimeError("boto3 and botocore are required for Bedrock embeddings. Install boto3.") from exc
    return boto3, Config


def _aws_session():
    boto3, _ = _load_boto3()
    profile = (getattr(settings, "aws_profile", "") or "").strip()
    region = (getattr(settings, "aws_region", "") or "us-east-1").strip()
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def _runtime_client():
    _, Config = _load_boto3()
    timeout = int(getattr(settings, "bedrock_request_timeout_seconds", 60) or 60)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return _aws_session().client("bedrock-runtime", region_name=getattr(settings, "aws_region", "us-east-1"), config=config)



def _bedrock_runtime_client():
    # Backward-compatible alias used by tests and older call sites.
    return _runtime_client()

def _embedding_request_body(text: str) -> dict[str, Any]:
    body: dict[str, Any] = {"inputText": text}
    dimensions = int(getattr(settings, "bedrock_embedding_dimensions", 0) or 0)
    if dimensions > 0:
        body["dimensions"] = dimensions
    if hasattr(settings, "bedrock_embedding_normalize_enabled"):
        body["normalize"] = bool(settings.bedrock_embedding_normalize_enabled)
    return body


def _extract_bedrock_embedding(payload: dict[str, Any]) -> list[float]:
    # Titan embeddings commonly return {"embedding": [...]}. Some models may
    # return embeddings under alternative keys; keep parsing defensive.
    candidates = [
        payload.get("embedding"),
        payload.get("embeddings"),
        payload.get("vector"),
    ]

    embeddings_by_type = payload.get("embeddingsByType")
    if isinstance(embeddings_by_type, dict):
        candidates.extend(
            [
                embeddings_by_type.get("float"),
                embeddings_by_type.get("float32"),
                embeddings_by_type.get("FLOAT32"),
            ]
        )

    for candidate in candidates:
        if isinstance(candidate, list) and candidate:
            if all(isinstance(item, (int, float)) for item in candidate):
                return [float(item) for item in candidate]
            if candidate and isinstance(candidate[0], list):
                return [float(item) for item in candidate[0]]

    raise ValueError("Amazon Bedrock returned an embedding payload without a float vector.")


def _embed_bedrock(text: str) -> list[float]:
    model_id = _bedrock_embedding_model_id()
    if not model_id:
        raise RuntimeError("BEDROCK_EMBEDDING_MODEL_ID is required when EMBEDDING_PROVIDER=bedrock.")
    if not (getattr(settings, "aws_region", "") or "").strip():
        raise RuntimeError("AWS_REGION is required when EMBEDDING_PROVIDER=bedrock.")

    response = _bedrock_runtime_client().invoke_model(
        modelId=model_id,
        body=json.dumps(_embedding_request_body(text)).encode("utf-8"),
        contentType="application/json",
        accept="application/json",
    )
    body = response.get("body") or response.get("Body")
    if hasattr(body, "read"):
        payload_bytes = body.read()
    else:
        payload_bytes = body or b"{}"
    if isinstance(payload_bytes, str):
        payload_bytes = payload_bytes.encode("utf-8")
    payload = json.loads(payload_bytes.decode("utf-8"))
    return _extract_bedrock_embedding(payload)


def get_embedding_provider_name() -> str:
    return _provider()


def get_embedding_model_name() -> str:
    provider = _provider()
    if provider == "huggingface":
        return _hf_model_name()
    if provider == "ollama":
        return _ollama_model_name()
    if provider == "bedrock":
        return _bedrock_embedding_model_id()
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")


def get_embedding_status() -> dict[str, Any]:
    provider = _provider()
    model = get_embedding_model_name()
    status = {
        "ok": True,
        "provider": provider,
        "model": model,
        "fallback_provider": _fallback_provider(),
        "configured": True,
        "aws_region": getattr(settings, "aws_region", "us-east-1"),
        "bedrock_embedding_model_id": _bedrock_embedding_model_id(),
        "bedrock_embedding_configured": bool(getattr(settings, "bedrock_embedding_configured", False)),
        "message": "Embedding provider is configured.",
    }

    if provider == "bedrock":
        configured = bool(getattr(settings, "bedrock_embedding_configured", False))
        status.update(
            {
                "ok": configured,
                "configured": configured,
                "dimensions": int(getattr(settings, "bedrock_embedding_dimensions", 0) or 0),
                "normalize": bool(getattr(settings, "bedrock_embedding_normalize_enabled", True)),
                "message": "Bedrock embeddings are configured." if configured else "Set AWS_REGION and BEDROCK_EMBEDDING_MODEL_ID.",
            }
        )
        try:
            _load_boto3()
            status["boto3_available"] = True
        except Exception as exc:
            status.update({"ok": False, "boto3_available": False, "message": str(exc)})
    elif provider == "ollama":
        status.update({"ollama_url": _ollama_url(), "ollama_model": _ollama_model_name()})
    else:
        status.update({"huggingface_model": _hf_model_name()})

    return status


def _embed_with_provider(provider: str, text: str) -> list[float]:
    if provider == "huggingface":
        return _embed_huggingface(text)
    if provider == "ollama":
        return _embed_ollama(text)
    if provider == "bedrock":
        return _embed_bedrock(text)
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {provider}")


def embed_text(text: str) -> List[float]:
    """Return one embedding vector using the configured provider."""
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    provider = _provider()
    started = time.perf_counter()
    try:
        vector = _embed_with_provider(provider, cleaned)
        record_operation(
            "embedding.embed_text",
            provider=provider,
            status="success",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            properties={
                "model": get_embedding_model_name(),
                "text_length": len(cleaned),
                "vector_dimensions": len(vector),
                "fallback_used": False,
            },
            extra_metrics={"EmbeddingDimensions": (float(len(vector)), "Count")},
        )
        return vector
    except Exception as exc:
        fallback = _fallback_provider()
        if fallback and fallback != "none" and fallback != provider:
            logger.warning(
                "[EMBEDDINGS] %s failed, falling back to %s: %s",
                provider,
                fallback,
                exc,
            )
            fallback_started = time.perf_counter()
            try:
                vector = _embed_with_provider(fallback, cleaned)
                record_operation(
                    "embedding.embed_text",
                    provider=fallback,
                    status="fallback_success",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    properties={
                        "primary_provider": provider,
                        "fallback_provider": fallback,
                        "fallback_used": True,
                        "fallback_reason": str(exc),
                        "text_length": len(cleaned),
                        "vector_dimensions": len(vector),
                        "fallback_latency_ms": round((time.perf_counter() - fallback_started) * 1000, 2),
                    },
                    extra_metrics={"EmbeddingDimensions": (float(len(vector)), "Count")},
                )
                return vector
            except Exception as fallback_exc:
                record_operation(
                    "embedding.embed_text",
                    provider=fallback,
                    status="error",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    properties={
                        "primary_provider": provider,
                        "fallback_provider": fallback,
                        "fallback_used": True,
                        "text_length": len(cleaned),
                    },
                    error=str(fallback_exc),
                )
                raise
        record_operation(
            "embedding.embed_text",
            provider=provider,
            status="error",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            properties={"text_length": len(cleaned), "fallback_used": False},
            error=str(exc),
        )
        raise


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for text in texts:
        cleaned = (text or "").strip()
        if not cleaned:
            continue
        vectors.append(embed_text(cleaned))
    return vectors
