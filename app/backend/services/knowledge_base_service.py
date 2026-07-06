from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.services.document_ingest_service import (
    ingest_document_revision,
    refresh_active_vector_store,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _rows(db: Session, sql: str, params: dict | None = None) -> list[dict[str, Any]]:
    return [dict(row) for row in db.execute(text(sql), params or {}).mappings().all()]


def _row(db: Session, sql: str, params: dict | None = None) -> dict[str, Any] | None:
    value = db.execute(text(sql), params or {}).mappings().first()
    return dict(value) if value else None


def _scalar(db: Session, sql: str, params: dict | None = None) -> int:
    value = db.execute(text(sql), params or {}).scalar()
    return int(value or 0)


def _clean_text(value: str | None) -> str | None:
    cleaned = (value or "").strip()
    return cleaned or None


def _clean_workflow(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned or cleaned.lower() in {"all", "any", "*"}:
        return None
    return cleaned


def _document_filters(
    *,
    query: str | None = None,
    workflow: str | None = None,
    active_only: bool | None = None,
    table_alias: str = "kd",
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}

    cleaned_query = _clean_text(query)
    if cleaned_query:
        params["query"] = f"%{cleaned_query.lower()}%"
        conditions.append(
            f"""
            (
                LOWER({table_alias}.source_document) LIKE :query
                OR LOWER({table_alias}.original_filename) LIKE :query
                OR LOWER({table_alias}.workflow) LIKE :query
                OR LOWER({table_alias}.file_hash) LIKE :query
                OR LOWER({table_alias}.uploaded_by) LIKE :query
            )
            """
        )

    cleaned_workflow = _clean_workflow(workflow)
    if cleaned_workflow:
        params["workflow"] = cleaned_workflow
        conditions.append(f"{table_alias}.workflow = :workflow")

    if active_only is True:
        conditions.append(f"{table_alias}.is_active IS TRUE")
    elif active_only is False:
        conditions.append(f"{table_alias}.is_active IS FALSE")

    if not conditions:
        return "", params

    return "WHERE " + " AND ".join(f"({condition})" for condition in conditions), params


def _chunk_filters(
    *,
    query: str | None = None,
    workflow: str | None = None,
    active_only: bool | None = None,
    table_alias: str = "dc",
) -> tuple[str, dict[str, Any]]:
    conditions: list[str] = []
    params: dict[str, Any] = {}

    cleaned_query = _clean_text(query)
    if cleaned_query:
        params["query"] = f"%{cleaned_query.lower()}%"
        conditions.append(
            f"""
            (
                LOWER({table_alias}.source_document) LIKE :query
                OR LOWER({table_alias}.workflow) LIKE :query
                OR LOWER({table_alias}.chunk_text) LIKE :query
                OR LOWER({table_alias}.chunk_metadata->>'original_filename') LIKE :query
                OR LOWER({table_alias}.chunk_metadata->>'file_hash') LIKE :query
            )
            """
        )

    cleaned_workflow = _clean_workflow(workflow)
    if cleaned_workflow:
        params["workflow"] = cleaned_workflow
        conditions.append(f"{table_alias}.workflow = :workflow")

    if active_only is True:
        conditions.append(f"{table_alias}.is_active IS TRUE")
    elif active_only is False:
        conditions.append(f"{table_alias}.is_active IS FALSE")

    if not conditions:
        return "", params

    return "WHERE " + " AND ".join(f"({condition})" for condition in conditions), params


def get_knowledge_base_snapshot(
    db: Session,
    chunk_limit: int = 50,
    *,
    query: str | None = None,
    workflow: str | None = None,
    active_only: bool | None = None,
) -> dict[str, Any]:
    document_where, document_params = _document_filters(
        query=query,
        workflow=workflow,
        active_only=active_only,
        table_alias="kd",
    )
    chunk_where, chunk_params = _chunk_filters(
        query=query,
        workflow=workflow,
        active_only=active_only,
        table_alias="dc",
    )

    active_documents = _scalar(
        db,
        """
        SELECT COUNT(DISTINCT source_document)
        FROM case4.knowledge_documents
        WHERE is_active IS TRUE
        """,
    )
    active_revisions = _scalar(
        db,
        """
        SELECT COUNT(*)
        FROM case4.knowledge_documents
        WHERE is_active IS TRUE
        """,
    )
    all_revisions = _scalar(db, "SELECT COUNT(*) FROM case4.knowledge_documents")
    active_chunks = _scalar(
        db,
        """
        SELECT COUNT(*)
        FROM case4.document_chunks
        WHERE is_active IS TRUE
        """,
    )
    all_chunks = _scalar(db, "SELECT COUNT(*) FROM case4.document_chunks")

    summary = {
        "active_documents": active_documents,
        "active_revisions": active_revisions,
        "all_revisions": all_revisions,
        "total_document_versions": all_revisions,
        "active_chunks": active_chunks,
        "all_chunks": all_chunks,
        "total_chunks": all_chunks,
        "active_workflows": _scalar(
            db,
            """
            SELECT COUNT(DISTINCT workflow)
            FROM case4.knowledge_documents
            WHERE is_active IS TRUE
            """,
        ),
        "last_indexed": _rows(
            db,
            """
            SELECT MAX(updated_at) AS last_indexed
            FROM case4.knowledge_documents
            """,
        )[0].get("last_indexed"),
        "filters": {
            "query": query,
            "workflow": workflow,
            "active_only": active_only,
            "chunk_limit": chunk_limit,
        },
    }

    documents = _rows(
        db,
        f"""
        WITH filtered_documents AS (
            SELECT kd.*
            FROM case4.knowledge_documents kd
            {document_where}
        )
        SELECT
            source_document,
            MAX(workflow) AS workflow,
            COUNT(*) AS revision_count,
            SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active_revision_count,
            MAX(revision_number) AS latest_revision_number,
            MAX(updated_at) AS last_updated,
            MAX(storage_type) AS storage_type,
            MAX(storage_path) AS storage_path,
            MAX(file_hash) AS latest_file_hash
        FROM filtered_documents
        GROUP BY source_document
        ORDER BY MAX(updated_at) DESC, source_document ASC
        """,
        document_params,
    )

    revisions = _rows(
        db,
        f"""
        SELECT
            kd.document_id,
            kd.source_document,
            kd.original_filename,
            kd.workflow,
            kd.revision_number,
            kd.file_hash,
            kd.storage_type,
            kd.storage_path,
            kd.mime_type,
            kd.uploaded_by,
            kd.is_active,
            kd.is_latest,
            kd.created_at,
            kd.updated_at,
            COALESCE(chunk_counts.chunk_count, 0) AS chunk_count,
            COALESCE(chunk_counts.active_chunk_count, 0) AS active_chunk_count
        FROM case4.knowledge_documents kd
        LEFT JOIN (
            SELECT
                chunk_metadata->>'document_id' AS document_id,
                COUNT(*) AS chunk_count,
                SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active_chunk_count
            FROM case4.document_chunks
            GROUP BY chunk_metadata->>'document_id'
        ) chunk_counts
          ON chunk_counts.document_id = kd.document_id
        {document_where}
        ORDER BY kd.source_document ASC, kd.revision_number DESC
        """,
        document_params,
    )

    workflow_breakdown = _rows(
        db,
        """
        SELECT
            workflow,
            COUNT(*) AS active_revision_count,
            COUNT(DISTINCT source_document) AS document_count
        FROM case4.knowledge_documents
        WHERE is_active IS TRUE
        GROUP BY workflow
        ORDER BY active_revision_count DESC, workflow ASC
        """,
    )

    chunks = _rows(
        db,
        f"""
        SELECT
            dc.chunk_id,
            dc.chunk_index,
            dc.source_document,
            dc.workflow,
            LEFT(dc.chunk_text, 500) AS chunk_preview,
            dc.embedding_model,
            dc.chunk_metadata->>'document_id' AS document_id,
            dc.chunk_metadata->>'revision_number' AS revision_number,
            dc.chunk_metadata->>'file_hash' AS file_hash,
            dc.chunk_metadata->>'storage_path' AS storage_path,
            dc.created_at,
            dc.updated_at,
            dc.chunk_metadata,
            dc.is_active
        FROM case4.document_chunks dc
        {chunk_where}
        ORDER BY dc.updated_at DESC, dc.source_document ASC, dc.chunk_index ASC
        LIMIT :chunk_limit
        """,
        {**chunk_params, "chunk_limit": chunk_limit},
    )

    return {
        "summary": summary,
        "workflow_breakdown": workflow_breakdown,
        "documents": documents,
        "revisions": revisions,
        "chunks": chunks,
    }


def get_document_revision(db: Session, document_id: str) -> dict[str, Any] | None:
    return _row(
        db,
        """
        SELECT
            kd.document_id,
            kd.source_document,
            kd.original_filename,
            kd.workflow,
            kd.revision_number,
            kd.file_hash,
            kd.storage_type,
            kd.storage_path,
            kd.mime_type,
            kd.uploaded_by,
            kd.is_active,
            kd.is_latest,
            kd.created_at,
            kd.updated_at,
            COALESCE(chunk_counts.chunk_count, 0) AS chunk_count,
            COALESCE(chunk_counts.active_chunk_count, 0) AS active_chunk_count
        FROM case4.knowledge_documents kd
        LEFT JOIN (
            SELECT
                chunk_metadata->>'document_id' AS document_id,
                COUNT(*) AS chunk_count,
                SUM(CASE WHEN is_active THEN 1 ELSE 0 END) AS active_chunk_count
            FROM case4.document_chunks
            GROUP BY chunk_metadata->>'document_id'
        ) chunk_counts
          ON chunk_counts.document_id = kd.document_id
        WHERE kd.document_id = :document_id
        LIMIT 1
        """,
        {"document_id": document_id},
    )


def get_document_file_info(db: Session, document_id: str) -> dict[str, Any] | None:
    row = get_document_revision(db, document_id)
    if not row:
        return None

    storage_path = Path(str(row.get("storage_path") or ""))
    return {
        "document_id": row.get("document_id"),
        "source_document": row.get("source_document"),
        "original_filename": row.get("original_filename"),
        "mime_type": row.get("mime_type") or "application/octet-stream",
        "storage_path": storage_path,
        "exists": storage_path.exists(),
    }


def search_knowledge_base(
    db: Session,
    *,
    query: str | None = None,
    workflow: str | None = None,
    active_only: bool | None = True,
    limit: int = 50,
) -> dict[str, Any]:
    limit = max(1, min(int(limit or 50), 500))
    payload = get_knowledge_base_snapshot(
        db,
        chunk_limit=limit,
        query=query,
        workflow=workflow,
        active_only=active_only,
    )
    return {
        "status": "ok",
        "query": query,
        "workflow": workflow,
        "active_only": active_only,
        "limit": limit,
        "documents": payload["documents"],
        "revisions": payload["revisions"],
        "chunks": payload["chunks"],
        "summary": {
            "document_count": len(payload["documents"]),
            "revision_count": len(payload["revisions"]),
            "chunk_count": len(payload["chunks"]),
        },
    }


def update_document_metadata(
    db: Session,
    document_id: str,
    *,
    workflow: str | None = None,
    uploaded_by: str | None = None,
    updated_by: str = "streamlit",
) -> dict[str, Any]:
    existing = get_document_revision(db, document_id)
    if not existing:
        raise ValueError(f"Document revision '{document_id}' was not found.")

    selected_workflow = _clean_workflow(workflow) or existing.get("workflow") or "general"
    selected_uploaded_by = _clean_text(uploaded_by) or existing.get("uploaded_by") or updated_by
    actor = _clean_text(updated_by) or "streamlit"

    db.execute(
        text(
            """
            UPDATE case4.knowledge_documents
            SET workflow = :workflow,
                uploaded_by = :uploaded_by,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE document_id = :document_id
            """
        ),
        {
            "document_id": document_id,
            "workflow": selected_workflow,
            "uploaded_by": selected_uploaded_by,
            "updated_by": actor,
            "updated_at": _now(),
        },
    )

    db.execute(
        text(
            """
            UPDATE case4.document_chunks
            SET workflow = :workflow,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE chunk_metadata->>'document_id' = :document_id
            """
        ),
        {
            "document_id": document_id,
            "workflow": selected_workflow,
            "updated_by": actor,
            "updated_at": _now(),
        },
    )

    db.commit()

    updated = get_document_revision(db, document_id) or existing
    return {
        "status": "updated",
        "message": f"Document revision '{document_id}' metadata updated.",
        "document": updated,
    }


def activate_document_revision(
    db: Session,
    document_id: str,
    *,
    updated_by: str = "streamlit",
) -> dict[str, Any]:
    target = get_document_revision(db, document_id)
    if not target:
        raise ValueError(f"Document revision '{document_id}' was not found.")

    source_document = str(target["source_document"])
    actor = _clean_text(updated_by) or "streamlit"
    now = _now()

    db.execute(
        text(
            """
            UPDATE case4.knowledge_documents
            SET is_active = false,
                is_latest = false,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE source_document = :source_document
            """
        ),
        {"source_document": source_document, "updated_by": actor, "updated_at": now},
    )

    db.execute(
        text(
            """
            UPDATE case4.document_chunks
            SET is_active = false,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE source_document = :source_document
            """
        ),
        {"source_document": source_document, "updated_by": actor, "updated_at": now},
    )

    db.execute(
        text(
            """
            UPDATE case4.knowledge_documents
            SET is_active = true,
                is_latest = true,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE document_id = :document_id
            """
        ),
        {"document_id": document_id, "updated_by": actor, "updated_at": now},
    )

    db.execute(
        text(
            """
            UPDATE case4.document_chunks
            SET is_active = true,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE chunk_metadata->>'document_id' = :document_id
            """
        ),
        {"document_id": document_id, "updated_by": actor, "updated_at": now},
    )

    db.commit()

    return {
        "status": "activated",
        "message": f"Revision {target['revision_number']} for '{source_document}' is now active.",
        "document_id": document_id,
        "source_document": source_document,
        "revision_number": target.get("revision_number"),
    }


def deactivate_document_revision(
    db: Session,
    document_id: str,
    *,
    updated_by: str = "streamlit",
) -> dict[str, Any]:
    target = get_document_revision(db, document_id)
    if not target:
        raise ValueError(f"Document revision '{document_id}' was not found.")

    source_document = str(target["source_document"])
    was_active = bool(target.get("is_active"))
    actor = _clean_text(updated_by) or "streamlit"
    now = _now()

    db.execute(
        text(
            """
            UPDATE case4.knowledge_documents
            SET is_active = false,
                is_latest = false,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE document_id = :document_id
            """
        ),
        {"document_id": document_id, "updated_by": actor, "updated_at": now},
    )

    db.execute(
        text(
            """
            UPDATE case4.document_chunks
            SET is_active = false,
                updated_by = :updated_by,
                updated_at = :updated_at
            WHERE chunk_metadata->>'document_id' = :document_id
            """
        ),
        {"document_id": document_id, "updated_by": actor, "updated_at": now},
    )

    promoted: dict[str, Any] | None = None
    if was_active:
        promoted = _row(
            db,
            """
            SELECT document_id, revision_number
            FROM case4.knowledge_documents
            WHERE source_document = :source_document
              AND document_id <> :document_id
            ORDER BY revision_number DESC
            LIMIT 1
            """,
            {"source_document": source_document, "document_id": document_id},
        )
        if promoted:
            db.execute(
                text(
                    """
                    UPDATE case4.knowledge_documents
                    SET is_active = true,
                        is_latest = true,
                        updated_by = :updated_by,
                        updated_at = :updated_at
                    WHERE document_id = :promoted_document_id
                    """
                ),
                {
                    "promoted_document_id": promoted["document_id"],
                    "updated_by": actor,
                    "updated_at": now,
                },
            )
            db.execute(
                text(
                    """
                    UPDATE case4.document_chunks
                    SET is_active = true,
                        updated_by = :updated_by,
                        updated_at = :updated_at
                    WHERE chunk_metadata->>'document_id' = :promoted_document_id
                    """
                ),
                {
                    "promoted_document_id": promoted["document_id"],
                    "updated_by": actor,
                    "updated_at": now,
                },
            )

    db.commit()

    return {
        "status": "deactivated",
        "message": f"Revision {target['revision_number']} for '{source_document}' was deactivated.",
        "document_id": document_id,
        "source_document": source_document,
        "revision_number": target.get("revision_number"),
        "promoted_document_id": promoted.get("document_id") if promoted else None,
        "promoted_revision_number": promoted.get("revision_number") if promoted else None,
    }


def upload_document_to_knowledge_base(
    db: Session,
    *,
    filename: str,
    content: bytes,
    workflow: str | None = None,
    uploaded_by: str = "streamlit",
    source_document_name: str | None = None,
    mime_type: str | None = None,
) -> dict[str, Any]:
    return ingest_document_revision(
        db,
        filename=filename,
        content=content,
        workflow=workflow,
        uploaded_by=uploaded_by,
        source_document_name=source_document_name,
        mime_type=mime_type,
    )


def refresh_knowledge_base(db: Session) -> dict[str, Any]:
    return refresh_active_vector_store(db)
