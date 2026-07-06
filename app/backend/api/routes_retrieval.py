from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.backend.services.retrieval_service import search_knowledge

router = APIRouter(prefix="/retrieve", tags=["retrieve"])


class RetrieveRequest(BaseModel):
    query: str = Field(..., min_length=1)
    workflow: str = "general"
    top_k: int = Field(default=3, ge=1, le=25)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)
    candidate_limit: int = Field(default=500, ge=1, le=2000)
    include_general: bool = True


@router.post("")
def retrieve(req: RetrieveRequest):
    return search_knowledge(
        query=req.query,
        workflow=req.workflow,
        top_k=req.top_k,
        min_score=req.min_score,
        candidate_limit=req.candidate_limit,
        include_general=req.include_general,
    )
