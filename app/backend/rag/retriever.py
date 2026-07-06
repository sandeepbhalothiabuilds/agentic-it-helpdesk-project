from __future__ import annotations

from typing import List, Dict
from app.backend.llm.mistral_client import chat_completion


def _normalize_query(text: str) -> str:
    return " ".join((text or "").strip().lower().replace("_", " ").split())


def build_retrieval_query(user_query: str, workflow: str) -> str:
    """
    Use Mistral to rewrite the user's wording into a short retrieval phrase.
    This is not hardcoded synonym mapping.
    """
    prompt = [
        {
            "role": "system",
            "content": (
                "You rewrite IT service desk user requests into short search phrases "
                "for document retrieval.\n"
                "Return only the search phrase.\n"
                "Do not explain."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Workflow: {workflow}\n"
                f"User request: {user_query}\n\n"
                "Return a short retrieval phrase that would likely appear in a runbook."
            ),
        },
    ]

    rewritten = chat_completion(prompt, temperature=0)
    rewritten = _normalize_query(rewritten)

    if not rewritten:
        return _normalize_query(user_query)

    return rewritten


def score_chunk(query: str, chunk_text: str) -> int:
    """
    Very small lexical scorer. The query has already been rewritten.
    """
    q_words = [w for w in _normalize_query(query).split() if len(w) > 2]
    text = _normalize_query(chunk_text)

    score = 0
    for word in q_words:
        if word in text:
            score += 1
    return score


def retrieve_chunks(
    user_query: str,
    workflow: str,
    corpus: List[Dict],
    top_k: int = 3,
) -> List[Dict]:
    """
    Filter by workflow tag first, then score by rewritten query.
    """
    retrieval_query = build_retrieval_query(user_query, workflow)

    candidates = [
        c for c in corpus
        if c.get("workflow") in {workflow, "general"}
    ]

    scored = []
    for item in candidates:
        score = score_chunk(retrieval_query, item["text"])
        if score > 0:
            scored.append(
                {
                    "source": item["source"],
                    "workflow": item["workflow"],
                    "chunk_id": item["chunk_id"],
                    "score": score,
                    "text": item["text"],
                }
            )

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:top_k]