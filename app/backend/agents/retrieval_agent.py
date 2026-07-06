from __future__ import annotations

from sqlalchemy.orm import Session

from app.backend.agents.common import get_or_create_request_id, safe_log_workflow_event
from app.backend.services.retrieval_service import search_knowledge


def retrieve_knowledge(db: Session, state: dict) -> dict:
    message = state.get("message", "")
    workflow = state.get("workflow", "clarify")
    employee_id = state.get("employee_id", "UNKNOWN")
    request_id = get_or_create_request_id(state)

    evidence = search_knowledge(
        query=message,
        workflow=workflow,
        top_k=5,
        min_score=0.02,
        include_general=True,
    )

    results = evidence.get("results", []) if isinstance(evidence, dict) else []

    safe_log_workflow_event(
        db=db,
        request_id=request_id,
        employee_id=employee_id,
        node_name="retrieve",
        stage="knowledge_retrieval",
        outcome="completed",
        details={
            "workflow": workflow,
            "result_count": len(results),
            "candidate_count": evidence.get("candidate_count") if isinstance(evidence, dict) else None,
            "retrieval_strategy": evidence.get("retrieval_strategy") if isinstance(evidence, dict) else None,
            "confidence": evidence.get("confidence") if isinstance(evidence, dict) else None,
        },
    )

    return {
        "request_id": request_id,
        "current_node": "retrieve",
        "evidence": evidence,
        "retrieved_documents": results,
        "retrievals": results,
        "documents": results,
        "chunks": results,
        "retrieval_confidence": evidence.get("confidence") if isinstance(evidence, dict) else "none",
        "retrieval_strategy": evidence.get("retrieval_strategy") if isinstance(evidence, dict) else "unknown",
        "workflow_outcome": "completed",
    }
