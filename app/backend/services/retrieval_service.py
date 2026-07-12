from __future__ import annotations

import math
import re
import time
from collections import Counter
from typing import Any, Iterable

import numpy as np
from sqlalchemy import or_

from app.backend.config import settings
from app.backend.db.models import DocumentChunk
from app.backend.db.session import SessionLocal
from app.backend.rag import bedrock_kb_service
from app.backend.rag.embedding_service import embed_text
from app.backend.telemetry import record_operation

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "me",
    "my",
    "of",
    "on",
    "or",
    "our",
    "please",
    "the",
    "this",
    "to",
    "with",
}

TOKEN_RE = re.compile(r"[a-zA-Z0-9_]+")


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0

    a_vec = np.asarray(a, dtype=np.float32)
    b_vec = np.asarray(b, dtype=np.float32)

    if a_vec.shape != b_vec.shape:
        return 0.0

    denom = float(np.linalg.norm(a_vec) * np.linalg.norm(b_vec))
    if denom == 0.0:
        return 0.0

    return float(np.dot(a_vec, b_vec) / denom)


def _tokens(text: str) -> list[str]:
    tokens = [token.lower() for token in TOKEN_RE.findall(text or "")]
    return [token for token in tokens if len(token) > 1 and token not in STOP_WORDS]


def _token_counter(text: str) -> Counter[str]:
    return Counter(_tokens(text))


def _lexical_score(query_tokens: list[str], chunk_text: str) -> tuple[float, list[str]]:
    if not query_tokens or not chunk_text:
        return 0.0, []

    chunk_counter = _token_counter(chunk_text)
    if not chunk_counter:
        return 0.0, []

    unique_query_terms = sorted(set(query_tokens))
    matched_terms = [term for term in unique_query_terms if term in chunk_counter]
    if not matched_terms:
        return 0.0, []

    coverage = len(matched_terms) / max(len(unique_query_terms), 1)
    density = sum(min(chunk_counter[term], 3) for term in matched_terms) / max(len(chunk_counter), 1)
    density = min(density * 4.0, 1.0)

    score = (coverage * 0.78) + (density * 0.22)
    return round(min(score, 1.0), 6), matched_terms


def _phrase_bonus(query: str, chunk_text: str) -> float:
    query_text = " ".join(_tokens(query))
    chunk_normalized = " ".join(_tokens(chunk_text))
    if not query_text or not chunk_normalized:
        return 0.0
    if query_text in chunk_normalized:
        return 0.06

    query_parts = query_text.split()
    if len(query_parts) < 2:
        return 0.0

    bigrams = [" ".join(query_parts[i : i + 2]) for i in range(len(query_parts) - 1)]
    matches = sum(1 for bigram in bigrams if bigram in chunk_normalized)
    if matches == 0:
        return 0.0
    return min(0.04, 0.015 * matches)


def _confidence(score: float) -> str:
    if score >= 0.78:
        return "high"
    if score >= 0.5:
        return "medium"
    if score > 0:
        return "low"
    return "none"


def _build_citation(row: DocumentChunk) -> dict[str, Any]:
    metadata = row.chunk_metadata or {}
    revision = metadata.get("revision_number")
    file_hash = metadata.get("file_hash")
    storage_path = metadata.get("storage_path")

    label = f"{row.source_document}#chunk-{row.chunk_index}"
    return {
        "label": label,
        "source_document": row.source_document,
        "chunk_id": row.chunk_id,
        "chunk_index": row.chunk_index,
        "revision_number": revision,
        "file_hash": file_hash,
        "storage_path": storage_path,
    }


def _deduplicate_results(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    best_by_key: dict[tuple[str, int], dict[str, Any]] = {}

    for item in results:
        key = (str(item.get("source_document") or item.get("source") or ""), int(item.get("chunk_index") or 0))
        existing = best_by_key.get(key)
        if existing is None or float(item.get("score") or 0) > float(existing.get("score") or 0):
            best_by_key[key] = item

    return list(best_by_key.values())


def _workflow_filters(workflow: str, include_general: bool) -> list[Any]:
    workflow_name = (workflow or "general").strip() or "general"
    filters = [DocumentChunk.workflow == workflow_name]
    if include_general and workflow_name != "general":
        filters.append(DocumentChunk.workflow == "general")
    return filters


def _result_from_row(
    *,
    row: DocumentChunk,
    query: str,
    query_tokens: list[str],
    query_embedding: list[float],
    workflow: str,
    semantic_weight: float,
    lexical_weight: float,
) -> dict[str, Any] | None:
    chunk_text = row.chunk_text or ""
    semantic_score = _cosine_similarity(query_embedding, row.embedding_json or []) if query_embedding else 0.0
    semantic_score = max(0.0, semantic_score)

    lexical_score, matched_terms = _lexical_score(query_tokens, chunk_text)
    bonus = _phrase_bonus(query, chunk_text)
    workflow_boost = 0.035 if row.workflow == workflow else 0.0

    if query_embedding:
        combined = (semantic_score * semantic_weight) + (lexical_score * lexical_weight) + bonus + workflow_boost
        strategy = "hybrid"
    else:
        combined = lexical_score + bonus + workflow_boost
        strategy = "lexical"

    combined = round(min(max(combined, 0.0), 1.0), 6)
    if combined <= 0:
        return None

    citation = _build_citation(row)
    reasons: list[str] = []
    if semantic_score > 0:
        reasons.append("semantic_match")
    if lexical_score > 0:
        reasons.append("keyword_match")
    if bonus > 0:
        reasons.append("phrase_match")
    if workflow_boost > 0:
        reasons.append("workflow_match")

    metadata = row.chunk_metadata or {}
    return {
        "chunk_id": row.chunk_id,
        "chunk_index": row.chunk_index,
        "source": row.source_document,
        "document_name": row.source_document,
        "source_document": row.source_document,
        "workflow": row.workflow,
        "score": round(combined, 4),
        "semantic_score": round(semantic_score, 4),
        "lexical_score": round(lexical_score, 4),
        "confidence": _confidence(combined),
        "matched_terms": matched_terms,
        "match_reasons": reasons,
        "citation": citation,
        "citation_label": citation["label"],
        "text": chunk_text,
        "preview": chunk_text[:500],
        "metadata": metadata,
        "retrieval_strategy": strategy,
    }


def _search_db_knowledge(
    query: str,
    workflow: str,
    top_k: int = 3,
    *,
    min_score: float = 0.0,
    candidate_limit: int = 500,
    include_general: bool = True,
    semantic_weight: float = 0.72,
    lexical_weight: float = 0.28,
) -> dict[str, Any]:
    """
    Retrieve evidence from the active PostgreSQL vector store.

    The ranking is hybrid:
    - semantic similarity when embeddings are available,
    - lexical keyword coverage as a deterministic fallback,
    - small boosts for phrase and workflow matches.

    The response intentionally keeps the legacy keys used by the chat UI while
    adding confidence, score components, matched terms, and citation metadata.
    """
    clean_query = (query or "").strip()
    clean_workflow = (workflow or "general").strip() or "general"
    top_k = max(1, min(int(top_k or 3), 25))
    candidate_limit = max(top_k, min(int(candidate_limit or 500), 2000))
    min_score = max(0.0, min(float(min_score or 0.0), 1.0))

    if not clean_query:
        return {
            "query": clean_query,
            "workflow": clean_workflow,
            "results": [],
            "source": "db",
            "retrieval_strategy": "empty_query",
            "candidate_count": 0,
            "result_count": 0,
            "top_k": top_k,
            "min_score": min_score,
            "confidence": "none",
        }

    query_tokens = _tokens(clean_query)
    query_embedding = embed_text(clean_query) or []
    strategy = "hybrid" if query_embedding else "lexical"

    raw_results: list[dict[str, Any]] = []
    candidate_count = 0

    with SessionLocal() as db:
        rows = (
            db.query(DocumentChunk)
            .filter(
                DocumentChunk.is_active.is_(True),
                or_(*_workflow_filters(clean_workflow, include_general)),
            )
            .order_by(
                DocumentChunk.workflow.asc(),
                DocumentChunk.source_document.asc(),
                DocumentChunk.chunk_index.asc(),
            )
            .limit(candidate_limit)
            .all()
        )

        candidate_count = len(rows)

        for row in rows:
            result = _result_from_row(
                row=row,
                query=clean_query,
                query_tokens=query_tokens,
                query_embedding=query_embedding,
                workflow=clean_workflow,
                semantic_weight=semantic_weight,
                lexical_weight=lexical_weight,
            )
            if result is None:
                continue
            if float(result["score"]) < min_score:
                continue
            raw_results.append(result)

    results = _deduplicate_results(raw_results)
    results.sort(
        key=lambda item: (
            float(item.get("score") or 0),
            float(item.get("semantic_score") or 0),
            float(item.get("lexical_score") or 0),
        ),
        reverse=True,
    )

    trimmed = results[:top_k]
    max_score = float(trimmed[0]["score"]) if trimmed else 0.0

    return {
        "query": clean_query,
        "workflow": clean_workflow,
        "results": trimmed,
        "source": "db",
        "retrieval_strategy": strategy,
        "candidate_count": candidate_count,
        "result_count": len(trimmed),
        "available_result_count": len(results),
        "top_k": top_k,
        "min_score": min_score,
        "confidence": _confidence(max_score),
        "score_components": {
            "semantic_weight": semantic_weight if query_embedding else 0.0,
            "lexical_weight": lexical_weight if query_embedding else 1.0,
            "phrase_bonus_max": 0.06,
            "workflow_boost": 0.035,
        },
    }


def search_knowledge(
    query: str,
    workflow: str,
    top_k: int = 3,
    *,
    min_score: float = 0.0,
    candidate_limit: int = 500,
    include_general: bool = True,
    semantic_weight: float = 0.72,
    lexical_weight: float = 0.28,
) -> dict[str, Any]:
    """Retrieve evidence through the configured provider.

    RETRIEVAL_PROVIDER=db keeps the PostgreSQL document_chunks path.
    RETRIEVAL_PROVIDER=bedrock_kb queries Amazon Bedrock Knowledge Bases and
    optionally falls back to PostgreSQL when RETRIEVAL_FALLBACK_TO_DB=true.
    """
    provider = settings.retrieval_provider_normalized
    started = time.perf_counter()
    telemetry_props = {
        "workflow": workflow,
        "top_k": top_k,
        "query_length": len(query or ""),
        "min_score": min_score,
        "candidate_limit": candidate_limit,
        "include_general": include_general,
    }
    if provider == "bedrock_kb":
        try:
            payload = bedrock_kb_service.retrieve_knowledge_base(
                query=query,
                workflow=workflow,
                top_k=top_k,
            )
            payload["fallback_used"] = False
            record_operation(
                "retrieval.search_knowledge",
                provider="bedrock_kb",
                status="success",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                properties={
                    **telemetry_props,
                    "result_count": payload.get("result_count"),
                    "candidate_count": payload.get("candidate_count"),
                    "confidence": payload.get("confidence"),
                    "fallback_used": False,
                },
                extra_metrics={"RetrievalResultCount": (float(payload.get("result_count") or 0), "Count")},
            )
            return payload
        except Exception as exc:
            if not settings.retrieval_db_fallback_enabled:
                record_operation(
                    "retrieval.search_knowledge",
                    provider="bedrock_kb",
                    status="error",
                    duration_ms=round((time.perf_counter() - started) * 1000, 2),
                    properties={**telemetry_props, "fallback_enabled": False},
                    error=str(exc),
                )
                raise
            fallback_payload = _search_db_knowledge(
                query=query,
                workflow=workflow,
                top_k=top_k,
                min_score=min_score,
                candidate_limit=candidate_limit,
                include_general=include_general,
                semantic_weight=semantic_weight,
                lexical_weight=lexical_weight,
            )
            fallback_payload["fallback_used"] = True
            fallback_payload["fallback_reason"] = str(exc)
            fallback_payload["requested_retrieval_provider"] = "bedrock_kb"
            record_operation(
                "retrieval.search_knowledge",
                provider="db",
                status="fallback_success",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                properties={
                    **telemetry_props,
                    "requested_provider": "bedrock_kb",
                    "fallback_used": True,
                    "fallback_reason": str(exc),
                    "result_count": fallback_payload.get("result_count"),
                    "candidate_count": fallback_payload.get("candidate_count"),
                    "confidence": fallback_payload.get("confidence"),
                },
                extra_metrics={"RetrievalResultCount": (float(fallback_payload.get("result_count") or 0), "Count")},
            )
            return fallback_payload

    payload = _search_db_knowledge(
        query=query,
        workflow=workflow,
        top_k=top_k,
        min_score=min_score,
        candidate_limit=candidate_limit,
        include_general=include_general,
        semantic_weight=semantic_weight,
        lexical_weight=lexical_weight,
    )
    payload["fallback_used"] = False
    payload["requested_retrieval_provider"] = provider
    record_operation(
        "retrieval.search_knowledge",
        provider=provider,
        status="success",
        duration_ms=round((time.perf_counter() - started) * 1000, 2),
        properties={
            **telemetry_props,
            "retrieval_strategy": payload.get("retrieval_strategy"),
            "result_count": payload.get("result_count"),
            "candidate_count": payload.get("candidate_count"),
            "confidence": payload.get("confidence"),
            "fallback_used": False,
        },
        extra_metrics={"RetrievalResultCount": (float(payload.get("result_count") or 0), "Count")},
    )
    return payload
