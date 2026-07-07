from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.db.session import SessionLocal, engine

SCHEMA_FILES = [
    "app/database/schema/case4_postgres_schema.sql",
    "app/database/schema/schema_workflow.sql",
    "app/database/schema/05_create_document_chunks.sql",
    "app/database/schema/06_workflow_events.sql",
    "app/database/schema/11_knowledge_documents.sql",
]

SEED_SQL_FILES = [
    "app/database/schema/case4_postgres_seed.sql",
]


def _resolve(path: str | Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return ROOT / candidate


def _run_sql_file(path: str | Path) -> None:
    resolved = _resolve(path)
    if not resolved.exists():
        raise FileNotFoundError(f"SQL file not found: {resolved}")

    print(f"[bootstrap] running SQL: {path}", flush=True)
    sql = resolved.read_text(encoding="utf-8")

    raw_connection = engine.raw_connection()
    try:
        cursor = raw_connection.cursor()
        try:
            cursor.execute(sql)
        finally:
            cursor.close()
        raw_connection.commit()
    except Exception:
        raw_connection.rollback()
        raise
    finally:
        raw_connection.close()


def run_sql_files(paths: Iterable[str | Path]) -> None:
    for path in paths:
        _run_sql_file(path)


def run_schema() -> None:
    run_sql_files(SCHEMA_FILES)


def run_seed_sql() -> None:
    run_sql_files(SEED_SQL_FILES)


def run_structured_seed() -> None:
    print("[bootstrap] loading structured CSV seed data", flush=True)
    from scripts.load_structured_data import seed_structured_data

    with SessionLocal() as db:
        result = seed_structured_data(db=db)
    print(f"[bootstrap] structured seed result: {result}", flush=True)


def run_knowledge_seed() -> None:
    print("[bootstrap] ingesting knowledge base seed documents", flush=True)
    from scripts.ingest_documents import seed_documents_from_directory

    seed_dir = ROOT / "data/knowledge_base/seed"
    with SessionLocal() as db:
        result = seed_documents_from_directory(db, seed_dir)
    print(f"[bootstrap] knowledge seed result: {result}", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the Agentic IT Service Desk database.")
    parser.add_argument("--schema", action="store_true", help="Run schema DDL files.")
    parser.add_argument("--seed-sql", action="store_true", help="Run SQL seed file.")
    parser.add_argument("--seed-structured", action="store_true", help="Load structured CSV seed data.")
    parser.add_argument("--seed-knowledge", action="store_true", help="Ingest seed knowledge-base documents.")
    args = parser.parse_args(argv)

    run_everything = not any([args.schema, args.seed_sql, args.seed_structured, args.seed_knowledge])

    if args.schema or run_everything:
        run_schema()

    if args.seed_sql or run_everything:
        run_seed_sql()

    if args.seed_structured or run_everything:
        run_structured_seed()

    if args.seed_knowledge or run_everything:
        run_knowledge_seed()

    print("[bootstrap] completed successfully", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
