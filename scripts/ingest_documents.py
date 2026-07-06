from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to Python path so `app.*` imports work when running the script directly.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.backend.db.session import SessionLocal
from app.backend.services.document_ingest_service import (
    SUPPORTED_EXTENSIONS,
    _infer_workflow_from_filename,
    ingest_document_revision,
    refresh_active_vector_store,
)


def iter_seed_files(seed_dir: Path):
    if not seed_dir.exists():
        return []
    files = []
    for path in sorted(seed_dir.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            files.append(path)
    return files


def seed_documents_from_directory(db, seed_dir: Path) -> dict:
    files = iter_seed_files(seed_dir)
    if not files:
        return {
            "seeded": 0,
            "skipped": 0,
            "message": f"No seed documents found in {seed_dir}",
        }

    seeded = 0
    skipped = 0
    results = []

    for path in files:
        content = path.read_bytes()
        workflow = _infer_workflow_from_filename(path.name)

        try:
            result = ingest_document_revision(
                db,
                filename=path.name,
                content=content,
                workflow=workflow,
                uploaded_by="seed-script",
                source_document_name=path.stem,
                mime_type=None,
            )
            results.append(result)
            if result.get("status") == "skipped":
                skipped += 1
            else:
                seeded += 1
        except Exception as exc:
            skipped += 1
            results.append(
                {
                    "status": "error",
                    "file": path.name,
                    "message": str(exc),
                }
            )

    return {
        "seeded": seeded,
        "skipped": skipped,
        "results": results,
        "message": f"Processed {len(files)} seed documents.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or refresh the knowledge base.")
    parser.add_argument(
        "--seed-dir",
        type=str,
        default="data/knowledge_base/seed",
        help="Directory containing initial knowledge documents.",
    )
    parser.add_argument(
        "--refresh-only",
        action="store_true",
        help="Skip seeding and refresh active documents from the database.",
    )
    args = parser.parse_args()

    seed_dir = Path(args.seed_dir)

    db = SessionLocal()
    try:
        print("=" * 80)
        print("KNOWLEDGE BASE INGEST / REFRESH")
        print("=" * 80)

        if args.refresh_only:
            result = refresh_active_vector_store(db)
            print(result)
            return

        seed_files = iter_seed_files(seed_dir)
        if seed_files:
            result = seed_documents_from_directory(db, seed_dir)
            print(result)
        else:
            print(f"No files found in {seed_dir}. Refreshing active knowledge base from DB.")
            result = refresh_active_vector_store(db)
            print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()