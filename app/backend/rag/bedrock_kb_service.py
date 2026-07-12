from __future__ import annotations

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
    except Exception as exc:  # pragma: no cover - dependency failure is environment-specific
        raise RuntimeError("boto3 and botocore are required for Bedrock Knowledge Bases retrieval.") from exc
    return boto3, Config


def _session():
    boto3, _ = _load_boto3()
    profile = (settings.aws_profile or "").strip()
    if profile:
        return boto3.Session(profile_name=profile, region_name=settings.aws_region)
    return boto3.Session(region_name=settings.aws_region)


def _client():
    _, Config = _load_boto3()
    timeout = int(getattr(settings, "bedrock_request_timeout_seconds", 60) or 60)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return _session().client("bedrock-agent-runtime", region_name=settings.aws_region, config=config)


def _location_to_dict(location: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(location, dict):
        return {}
    return location


def _citation_label(item: dict[str, Any], index: int) -> str:
    location = _location_to_dict(item.get("location"))
    if location.get("type") == "S3" and isinstance(location.get("s3Location"), dict):
        uri = location["s3Location"].get("uri") or "s3://unknown"
        return f"Bedrock KB citation {index}: {uri}"
    if location.get("type"):
        return f"Bedrock KB citation {index}: {location.get('type')}"
    return f"Bedrock KB citation {index}"


def _result_from_bedrock_item(item: dict[str, Any], index: int, workflow: str) -> dict[str, Any]:
    content = item.get("content") if isinstance(item.get("content"), dict) else {}
    text = str(content.get("text") or "").strip()
    metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
    location = _location_to_dict(item.get("location"))
    score = float(item.get("score") or 0.0)
    source_document = (
        metadata.get("source_document")
        or metadata.get("x-amz-bedrock-kb-source-uri")
        or metadata.get("source")
        or _citation_label(item, index)
    )
    citation = {
        "label": _citation_label(item, index),
        "source_document": source_document,
        "chunk_id": f"bedrock-kb-{index}",
        "chunk_index": index - 1,
        "location": location,
        "metadata": metadata,
    }
    return {
        "chunk_id": f"bedrock-kb-{index}",
        "chunk_index": index - 1,
        "source": source_document,
        "document_name": source_document,
        "source_document": source_document,
        "workflow": workflow,
        "score": round(score, 4),
        "semantic_score": round(score, 4),
        "lexical_score": 0.0,
        "confidence": "high" if score >= 0.78 else "medium" if score >= 0.5 else "low" if score > 0 else "none",
        "matched_terms": [],
        "match_reasons": ["bedrock_knowledge_base"],
        "citation": citation,
        "citation_label": citation["label"],
        "text": text,
        "preview": text[:500],
        "metadata": metadata,
        "location": location,
        "retrieval_strategy": "bedrock_kb",
    }


def retrieve_knowledge_base(
    *,
    query: str,
    workflow: str = "general",
    top_k: int = 3,
    search_type: str | None = None,
) -> dict[str, Any]:
    clean_query = (query or "").strip()
    clean_workflow = (workflow or "general").strip() or "general"
    top_k = max(1, min(int(top_k or settings.bedrock_kb_number_of_results or 3), 25))
    knowledge_base_id = (settings.bedrock_knowledge_base_id or "").strip()
    if not knowledge_base_id:
        raise RuntimeError("BEDROCK_KNOWLEDGE_BASE_ID is required when RETRIEVAL_PROVIDER=bedrock_kb.")
    if not clean_query:
        return {
            "query": clean_query,
            "workflow": clean_workflow,
            "results": [],
            "source": "bedrock_kb",
            "retrieval_strategy": "empty_query",
            "candidate_count": 0,
            "result_count": 0,
            "top_k": top_k,
            "confidence": "none",
        }

    selected_search_type = (search_type or settings.bedrock_kb_search_type or "HYBRID").strip().upper()
    vector_config: dict[str, Any] = {"numberOfResults": top_k}
    if selected_search_type in {"HYBRID", "SEMANTIC"}:
        vector_config["overrideSearchType"] = selected_search_type

    started = time.perf_counter()
    telemetry_props = {
        "knowledge_base_id_set": bool(knowledge_base_id),
        "workflow": clean_workflow,
        "top_k": top_k,
        "search_type": selected_search_type,
        "query_length": len(clean_query),
    }
    try:
        response = _client().retrieve(
            knowledgeBaseId=knowledge_base_id,
            retrievalQuery={"text": clean_query},
            retrievalConfiguration={"vectorSearchConfiguration": vector_config},
        )
        retrieval_results = response.get("retrievalResults", []) or []
        results = [
            _result_from_bedrock_item(item, idx, clean_workflow)
            for idx, item in enumerate(retrieval_results, start=1)
            if isinstance(item, dict)
        ]
        max_score = float(results[0].get("score") or 0.0) if results else 0.0
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        record_operation(
            "retrieval.bedrock_kb.retrieve",
            provider="bedrock_kb",
            status="success",
            duration_ms=duration_ms,
            properties={**telemetry_props, "result_count": len(results), "candidate_count": len(retrieval_results)},
            extra_metrics={"RetrievalResultCount": (float(len(results)), "Count")},
        )
        return {
            "query": clean_query,
            "workflow": clean_workflow,
            "results": results,
            "source": "bedrock_kb",
            "retrieval_strategy": "bedrock_kb",
            "candidate_count": len(retrieval_results),
            "result_count": len(results),
            "available_result_count": len(results),
            "top_k": top_k,
            "confidence": "high" if max_score >= 0.78 else "medium" if max_score >= 0.5 else "low" if max_score > 0 else "none",
            "knowledge_base_id": knowledge_base_id,
            "search_type": selected_search_type,
            "latency_ms": duration_ms,
        }
    except Exception as exc:
        record_operation(
            "retrieval.bedrock_kb.retrieve",
            provider="bedrock_kb",
            status="error",
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
            properties=telemetry_props,
            error=str(exc),
        )
        raise


def get_bedrock_kb_status() -> dict[str, Any]:
    configured = bool(settings.bedrock_kb_configured)
    try:
        _load_boto3()
        boto3_available = True
    except Exception as exc:
        return {
            "ok": False,
            "configured": configured,
            "provider": "bedrock_kb",
            "boto3_available": False,
            "knowledge_base_id_set": bool(settings.bedrock_knowledge_base_id),
            "region": settings.aws_region,
            "message": str(exc),
        }

    return {
        "ok": configured,
        "configured": configured,
        "provider": "bedrock_kb",
        "boto3_available": boto3_available,
        "knowledge_base_id_set": bool(settings.bedrock_knowledge_base_id),
        "data_source_id_set": bool(settings.bedrock_kb_data_source_id),
        "region": settings.aws_region,
        "number_of_results": settings.bedrock_kb_number_of_results,
        "search_type": settings.bedrock_kb_search_type,
        "message": "Bedrock Knowledge Base retrieval is configured." if configured else "Set BEDROCK_KNOWLEDGE_BASE_ID to use Bedrock Knowledge Bases.",
    }
