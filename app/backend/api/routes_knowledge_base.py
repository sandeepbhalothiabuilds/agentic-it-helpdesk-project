from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.backend.db.session import get_db
from app.backend.services.knowledge_base_service import (
    activate_document_revision,
    deactivate_document_revision,
    get_document_file_content,
    get_document_file_info,
    get_document_revision,
    get_knowledge_base_snapshot,
    refresh_knowledge_base,
    search_knowledge_base,
    update_document_metadata,
    upload_document_to_knowledge_base,
)

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])


class KnowledgeDocumentUpdate(BaseModel):
    workflow: str | None = None
    uploaded_by: str | None = None
    updated_by: str = "streamlit"


class KnowledgeDocumentAction(BaseModel):
    updated_by: str = "streamlit"


def _handle_value_error(exc: ValueError) -> None:
    raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/summary")
def knowledge_base_summary(
    chunk_limit: int = Query(default=50, ge=1, le=500),
    query: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    active_only: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    return get_knowledge_base_snapshot(
        db,
        chunk_limit=chunk_limit,
        query=query,
        workflow=workflow,
        active_only=active_only,
    )


@router.get("/documents")
def knowledge_base_documents(
    chunk_limit: int = Query(default=50, ge=1, le=500),
    query: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    active_only: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = get_knowledge_base_snapshot(
        db,
        chunk_limit=chunk_limit,
        query=query,
        workflow=workflow,
        active_only=active_only,
    )
    return {
        "summary": payload["summary"],
        "workflow_breakdown": payload["workflow_breakdown"],
        "documents": payload["documents"],
        "revisions": payload["revisions"],
    }


@router.get("/revisions")
def knowledge_base_revisions(
    chunk_limit: int = Query(default=50, ge=1, le=500),
    query: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    active_only: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = get_knowledge_base_snapshot(
        db,
        chunk_limit=chunk_limit,
        query=query,
        workflow=workflow,
        active_only=active_only,
    )
    return {
        "summary": payload["summary"],
        "revisions": payload["revisions"],
    }


@router.get("/chunks")
def knowledge_base_chunks(
    chunk_limit: int = Query(default=50, ge=1, le=500),
    query: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    active_only: bool | None = Query(default=None),
    db: Session = Depends(get_db),
):
    payload = get_knowledge_base_snapshot(
        db,
        chunk_limit=chunk_limit,
        query=query,
        workflow=workflow,
        active_only=active_only,
    )
    return {
        "summary": payload["summary"],
        "chunks": payload["chunks"],
    }


@router.get("/search")
def knowledge_base_search(
    query: str | None = Query(default=None),
    workflow: str | None = Query(default=None),
    active_only: bool | None = Query(default=True),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return search_knowledge_base(
        db,
        query=query,
        workflow=workflow,
        active_only=active_only,
        limit=limit,
    )


@router.get("/documents/{document_id}")
def knowledge_base_document_detail(
    document_id: str,
    db: Session = Depends(get_db),
):
    document = get_document_revision(db, document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document revision '{document_id}' was not found.")
    return {"document": document}


@router.get("/documents/{document_id}/download")
def knowledge_base_document_download(
    document_id: str,
    db: Session = Depends(get_db),
):
    file_info = get_document_file_info(db, document_id)
    if not file_info:
        raise HTTPException(status_code=404, detail=f"Document revision '{document_id}' was not found.")

    if not file_info.get("exists"):
        raise HTTPException(
            status_code=404,
            detail=f"Stored file for document revision '{document_id}' was not found.",
        )

    if str(file_info.get("storage_type") or "local").lower() == "s3":
        payload = get_document_file_content(db, document_id)
        if not payload:
            raise HTTPException(
                status_code=404,
                detail=f"Stored file for document revision '{document_id}' was not found.",
            )
        content_info, content = payload
        filename = str(content_info.get("original_filename") or f"{document_id}.bin")
        return StreamingResponse(
            iter([content]),
            media_type=str(content_info.get("mime_type") or "application/octet-stream"),
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    storage_path = file_info["storage_path"]
    if not isinstance(storage_path, Path):
        storage_path = Path(str(storage_path or ""))

    return FileResponse(
        path=str(storage_path),
        media_type=str(file_info.get("mime_type") or "application/octet-stream"),
        filename=str(file_info.get("original_filename") or storage_path.name),
    )


@router.patch("/documents/{document_id}")
def knowledge_base_document_update(
    document_id: str,
    payload: KnowledgeDocumentUpdate,
    db: Session = Depends(get_db),
):
    try:
        return update_document_metadata(
            db,
            document_id,
            workflow=payload.workflow,
            uploaded_by=payload.uploaded_by,
            updated_by=payload.updated_by,
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post("/documents/{document_id}/activate")
def knowledge_base_document_activate(
    document_id: str,
    payload: KnowledgeDocumentAction | None = None,
    db: Session = Depends(get_db),
):
    try:
        return activate_document_revision(
            db,
            document_id,
            updated_by=(payload.updated_by if payload else "streamlit"),
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post("/documents/{document_id}/deactivate")
def knowledge_base_document_deactivate(
    document_id: str,
    payload: KnowledgeDocumentAction | None = None,
    db: Session = Depends(get_db),
):
    try:
        return deactivate_document_revision(
            db,
            document_id,
            updated_by=(payload.updated_by if payload else "streamlit"),
        )
    except ValueError as exc:
        _handle_value_error(exc)


@router.post("/upload")
def knowledge_base_upload(
    file: UploadFile = File(...),
    workflow: str = Form(default="general"),
    uploaded_by: str = Form(default="streamlit"),
    source_document_name: str = Form(default=""),
    db: Session = Depends(get_db),
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="A filename is required.")

    content = file.file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    return upload_document_to_knowledge_base(
        db,
        filename=file.filename,
        content=content,
        workflow=workflow or "general",
        uploaded_by=uploaded_by or "streamlit",
        source_document_name=source_document_name or None,
        mime_type=file.content_type,
    )


@router.post("/refresh")
def knowledge_base_refresh(db: Session = Depends(get_db)):
    return refresh_knowledge_base(db)
