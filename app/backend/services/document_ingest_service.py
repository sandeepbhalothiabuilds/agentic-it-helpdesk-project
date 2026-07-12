from __future__ import annotations

import hashlib
import mimetypes
import re
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.config import settings
from app.backend.db.models import DocumentChunk
from app.backend.rag.chunking import chunk_text
from app.backend.rag.embedding_service import embed_text, get_embedding_model_name
from app.backend.storage.s3_storage import build_s3_key, get_object_bytes, put_object_bytes

KB_STORAGE_ROOT = Path(settings.kb_storage_root)
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    try:
        import json

        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _sanitize_name(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.strip("._-")
    return cleaned or "document"


def _infer_workflow_from_filename(filename: str) -> str:
    name = (filename or "").lower()

    rules = [
        ("password_reset", ["password", "credential", "identity verification"]),
        ("account_unlock", ["unlock", "lockout", "locked out", "account lock"]),
        ("vpn_reenable", ["vpn", "remote access", "remote_access", "tunnel"]),
    ]

    for workflow, keywords in rules:
        if any(keyword in name for keyword in keywords):
            return workflow

    return "general"


def _extract_text_from_docx(content: bytes) -> str:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError(
            "python-docx is required for .docx ingestion. Install it with pip install python-docx."
        ) from exc

    doc = Document(BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
    return "\n".join(paragraphs).strip()


def _extract_text_from_pdf(content: bytes) -> str:
    try:
        from PyPDF2 import PdfReader
    except ImportError as exc:
        raise RuntimeError(
            "PyPDF2 is required for .pdf ingestion. Install it with pip install PyPDF2."
        ) from exc

    reader = PdfReader(BytesIO(content))
    pages: list[str] = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n".join(pages).strip()


def _extract_text_from_plain_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore").strip()


def extract_text_from_uploaded_file(filename: str, content: bytes) -> str:
    suffix = Path(filename).suffix.lower()

    if suffix == ".docx":
        return _extract_text_from_docx(content)
    if suffix == ".pdf":
        return _extract_text_from_pdf(content)
    return _extract_text_from_plain_text(content)


def _selected_storage_type(storage_type: str | None = None) -> str:
    requested = (storage_type or "").strip().lower()
    if requested in {"local", "s3"}:
        return requested
    return settings.kb_storage_backend_normalized


def _save_local_document_file(
    *,
    source_document: str,
    revision_number: int,
    original_filename: str,
    content: bytes,
) -> Path:
    safe_source = _sanitize_name(source_document)
    safe_original = _sanitize_name(original_filename)
    target_dir = Path(settings.kb_storage_root) / safe_source / f"rev_{revision_number:03d}"
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / safe_original
    target_path.write_bytes(content)
    return target_path


def _save_document_file(
    *,
    source_document: str,
    revision_number: int,
    original_filename: str,
    content: bytes,
    mime_type: str | None = None,
    file_hash: str | None = None,
    storage_type: str | None = None,
) -> tuple[str, str]:
    selected_storage = _selected_storage_type(storage_type)
    if selected_storage == "s3":
        safe_source = _sanitize_name(source_document)
        safe_original = _sanitize_name(original_filename)
        key = build_s3_key(safe_source, f"rev_{revision_number:03d}", safe_original)
        ref = put_object_bytes(
            content=content,
            key=key,
            content_type=mime_type or mimetypes.guess_type(original_filename)[0],
            metadata={
                "source_document": source_document,
                "original_filename": original_filename,
                "revision_number": str(revision_number),
                "file_hash": file_hash or hashlib.sha256(content).hexdigest(),
            },
        )
        return "s3", ref.uri

    target_path = _save_local_document_file(
        source_document=source_document,
        revision_number=revision_number,
        original_filename=original_filename,
        content=content,
    )
    return "local", str(target_path)


def _read_stored_document(storage_type: str | None, storage_path: str) -> bytes:
    selected_storage = (storage_type or "local").strip().lower()
    if selected_storage == "s3" or str(storage_path).startswith("s3://"):
        return get_object_bytes(storage_path)

    path = Path(storage_path)
    if not path.exists():
        raise FileNotFoundError(f"Missing file at {storage_path}")
    return path.read_bytes()


def _deactivate_existing_document_state(db: Session, source_document: str) -> None:
    db.execute(
        text(
            """
            UPDATE case4.knowledge_documents
            SET is_active = false,
                is_latest = false,
                updated_at = :updated_at,
                updated_by = :updated_by
            WHERE source_document = :source_document
            """
        ),
        {
            "source_document": source_document,
            "updated_at": _now(),
            "updated_by": "system",
        },
    )

    db.execute(
        text(
            """
            UPDATE case4.document_chunks
            SET is_active = false
            WHERE source_document = :source_document
            """
        ),
        {"source_document": source_document},
    )


def _latest_revision_number(db: Session, source_document: str) -> int:
    value = db.execute(
        text(
            """
            SELECT COALESCE(MAX(revision_number), 0)
            FROM case4.knowledge_documents
            WHERE source_document = :source_document
            """
        ),
        {"source_document": source_document},
    ).scalar()
    return int(value or 0)


def _latest_active_document_row(db: Session, source_document: str) -> dict[str, Any] | None:
    row = db.execute(
        text(
            """
            SELECT
                document_id,
                source_document,
                original_filename,
                workflow,
                revision_number,
                file_hash,
                storage_type,
                storage_path,
                mime_type,
                uploaded_by,
                is_active,
                is_latest,
                created_at,
                updated_at
            FROM case4.knowledge_documents
            WHERE source_document = :source_document
              AND is_active = true
            ORDER BY revision_number DESC
            LIMIT 1
            """
        ),
        {"source_document": source_document},
    ).mappings().first()

    return dict(row) if row else None


def _insert_document_row(
    db: Session,
    *,
    document_id: str,
    source_document: str,
    original_filename: str,
    workflow: str,
    revision_number: int,
    file_hash: str,
    storage_type: str,
    storage_path: str,
    mime_type: str | None,
    uploaded_by: str,
) -> None:
    db.execute(
        text(
            """
            INSERT INTO case4.knowledge_documents (
                document_id,
                source_document,
                original_filename,
                workflow,
                revision_number,
                file_hash,
                storage_type,
                storage_path,
                mime_type,
                uploaded_by,
                is_active,
                is_latest,
                created_by,
                updated_by,
                created_at,
                updated_at
            )
            VALUES (
                :document_id,
                :source_document,
                :original_filename,
                :workflow,
                :revision_number,
                :file_hash,
                :storage_type,
                :storage_path,
                :mime_type,
                :uploaded_by,
                true,
                true,
                :created_by,
                :updated_by,
                :created_at,
                :updated_at
            )
            """
        ),
        {
            "document_id": document_id,
            "source_document": source_document,
            "original_filename": original_filename,
            "workflow": workflow,
            "revision_number": revision_number,
            "file_hash": file_hash,
            "storage_type": storage_type,
            "storage_path": storage_path,
            "mime_type": mime_type,
            "uploaded_by": uploaded_by,
            "created_by": uploaded_by,
            "updated_by": uploaded_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )


def _insert_document_chunks(
    db: Session,
    *,
    document_id: str,
    source_document: str,
    original_filename: str,
    workflow: str,
    revision_number: int,
    file_hash: str,
    storage_type: str,
    storage_path: str,
    uploaded_by: str,
    chunks: list[str],
) -> int:
    embedding_model = get_embedding_model_name()
    inserted = 0

    for idx, chunk in enumerate(chunks):
        chunk_id = hashlib.sha1(
            f"{document_id}|{source_document}|{revision_number}|{idx}|{chunk}".encode("utf-8")
        ).hexdigest()

        embedding = embed_text(chunk)
        if not embedding:
            continue

        row = DocumentChunk(
            chunk_id=chunk_id,
            source_document=source_document,
            workflow=workflow,
            chunk_index=idx,
            chunk_text=chunk,
            embedding_model=embedding_model,
            embedding_json=embedding,
            chunk_metadata={
                "document_id": document_id,
                "source_document": source_document,
                "original_filename": original_filename,
                "workflow": workflow,
                "revision_number": revision_number,
                "file_hash": file_hash,
                "storage_type": storage_type,
                "storage_path": storage_path,
                "uploaded_by": uploaded_by,
            },
            created_by=uploaded_by,
            updated_by=uploaded_by,
            is_active=True,
        )
        db.add(row)
        inserted += 1

    return inserted


def ingest_document_revision(
    db: Session,
    *,
    filename: str,
    content: bytes,
    workflow: str | None = None,
    uploaded_by: str = "system",
    source_document_name: str | None = None,
    mime_type: str | None = None,
    storage_type: str = "auto",
) -> dict[str, Any]:
    """Ingest a new document or a new revision of an existing document."""
    if not content:
        raise ValueError("Uploaded file is empty.")

    original_filename = Path(filename).name
    logical_source_document = (source_document_name or Path(filename).stem).strip()
    if not logical_source_document:
        logical_source_document = Path(filename).stem

    selected_workflow = (workflow or "").strip() or _infer_workflow_from_filename(original_filename)
    file_hash = hashlib.sha256(content).hexdigest()
    selected_mime_type = mime_type or mimetypes.guess_type(original_filename)[0]
    selected_storage_type = _selected_storage_type(storage_type)

    active_row = _latest_active_document_row(db, logical_source_document)
    if active_row and str(active_row.get("file_hash") or "") == file_hash:
        return {
            "status": "skipped",
            "message": "This exact document revision is already indexed.",
            "document_id": active_row.get("document_id"),
            "source_document": logical_source_document,
            "original_filename": original_filename,
            "workflow": active_row.get("workflow") or selected_workflow,
            "revision_number": active_row.get("revision_number"),
            "file_hash": file_hash,
            "storage_type": active_row.get("storage_type") or selected_storage_type,
            "storage_type": active_row.get("storage_type"),
            "storage_path": active_row.get("storage_path"),
            "chunks_inserted": 0,
            "embedding_model": get_embedding_model_name(),
        }

    revision_number = _latest_revision_number(db, logical_source_document) + 1
    document_id = f"DOC-{uuid4().hex[:10].upper()}"

    actual_storage_type, storage_path = _save_document_file(
        source_document=logical_source_document,
        revision_number=revision_number,
        original_filename=original_filename,
        content=content,
        mime_type=selected_mime_type,
        file_hash=file_hash,
        storage_type=selected_storage_type,
    )

    extracted_text = extract_text_from_uploaded_file(original_filename, content)
    if not extracted_text.strip():
        raise ValueError(
            f"Could not extract any text from '{original_filename}'. "
            "Please upload a readable PDF, DOCX, TXT, or MD file."
        )

    chunks = chunk_text(extracted_text)
    if not chunks:
        raise ValueError(f"No chunks could be created from '{original_filename}'.")

    try:
        _deactivate_existing_document_state(db, logical_source_document)

        _insert_document_row(
            db,
            document_id=document_id,
            source_document=logical_source_document,
            original_filename=original_filename,
            workflow=selected_workflow,
            revision_number=revision_number,
            file_hash=file_hash,
            storage_type=actual_storage_type,
            storage_path=storage_path,
            mime_type=selected_mime_type,
            uploaded_by=uploaded_by,
        )

        inserted = _insert_document_chunks(
            db,
            document_id=document_id,
            source_document=logical_source_document,
            original_filename=original_filename,
            workflow=selected_workflow,
            revision_number=revision_number,
            file_hash=file_hash,
            storage_type=actual_storage_type,
            storage_path=storage_path,
            uploaded_by=uploaded_by,
            chunks=chunks,
        )

        db.commit()

        return {
            "status": "indexed",
            "message": f"Indexed '{logical_source_document}' successfully.",
            "document_id": document_id,
            "source_document": logical_source_document,
            "original_filename": original_filename,
            "workflow": selected_workflow,
            "revision_number": revision_number,
            "file_hash": file_hash,
            "storage_type": actual_storage_type,
            "storage_path": storage_path,
            "chunks_inserted": inserted,
            "embedding_model": get_embedding_model_name(),
        }
    except Exception:
        db.rollback()
        raise


def refresh_active_vector_store(db: Session) -> dict[str, Any]:
    """Rebuild the vector store from active knowledge_documents rows."""
    rows = db.execute(
        text(
            """
            SELECT
                document_id,
                source_document,
                original_filename,
                workflow,
                revision_number,
                file_hash,
                storage_type,
                storage_path,
                mime_type,
                uploaded_by
            FROM case4.knowledge_documents
            WHERE is_active = true
            ORDER BY source_document ASC, revision_number DESC
            """
        )
    ).mappings().all()

    refreshed_documents = 0
    refreshed_chunks = 0
    skipped_documents: list[dict[str, Any]] = []

    for row in rows:
        record = dict(row)
        try:
            content = _read_stored_document(record.get("storage_type"), str(record["storage_path"]))
        except Exception as exc:
            skipped_documents.append(
                {
                    "source_document": record["source_document"],
                    "reason": str(exc),
                    "storage_type": record.get("storage_type") or "local",
                    "storage_path": record.get("storage_path"),
                }
            )
            continue

        extracted_text = extract_text_from_uploaded_file(record["original_filename"], content)
        if not extracted_text.strip():
            skipped_documents.append(
                {
                    "source_document": record["source_document"],
                    "reason": "No text could be extracted",
                    "storage_type": record.get("storage_type") or "local",
                    "storage_path": record.get("storage_path"),
                }
            )
            continue

        chunks = chunk_text(extracted_text)
        if not chunks:
            skipped_documents.append(
                {
                    "source_document": record["source_document"],
                    "reason": "No chunks produced",
                    "storage_type": record.get("storage_type") or "local",
                    "storage_path": record.get("storage_path"),
                }
            )
            continue

        try:
            db.query(DocumentChunk).filter(
                DocumentChunk.source_document == record["source_document"]
            ).update(
                {DocumentChunk.is_active: False},
                synchronize_session=False,
            )

            refreshed_chunks += _insert_document_chunks(
                db,
                document_id=record["document_id"],
                source_document=record["source_document"],
                original_filename=record["original_filename"],
                workflow=record["workflow"],
                revision_number=int(record["revision_number"]),
                file_hash=record["file_hash"],
                storage_type=record.get("storage_type") or "local",
                storage_path=record["storage_path"],
                uploaded_by=record["uploaded_by"] or "system",
                chunks=chunks,
            )
            refreshed_documents += 1
        except Exception:
            db.rollback()
            raise

    db.commit()

    return {
        "status": "refreshed",
        "message": "Vector store refresh completed.",
        "documents_refreshed": refreshed_documents,
        "chunks_refreshed": refreshed_chunks,
        "skipped_documents": skipped_documents,
        "embedding_model": get_embedding_model_name(),
        "storage_backend": settings.kb_storage_backend_normalized,
    }
