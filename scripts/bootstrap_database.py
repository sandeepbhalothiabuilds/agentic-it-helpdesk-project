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


def _existing_files(paths: Iterable[str]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        candidate = ROOT / path
        if candidate.exists():
            files.append(candidate)
        else:
            print(f"[bootstrap] skipping missing file: {candidate}")
    return files


def run_sql_files(paths: Iterable[str]) -> None:
    files = _existing_files(paths)
    if not files:
        print("[bootstrap] no SQL files to run")
        return

    with engine.begin() as conn:
        for file_path in files:
            print(f"[bootstrap] running SQL: {file_path.relative_to(ROOT)}")
            sql = file_path.read_text(encoding="utf-8")
            if sql.strip():
                conn.exec_driver_sql(sql)


def seed_structured_data() -> None:
    from scripts.load_structured_data import seed_structured_data as load_structured

    db = SessionLocal()
    try:
        print("[bootstrap] loading structured CSV seed data")
        result = load_structured(db)
        print(f"[bootstrap] structured seed result: {result}")
    finally:
        db.close()


def seed_knowledge_base(seed_dir: str = "data/knowledge_base/seed") -> None:
    from scripts.ingest_documents import seed_documents_from_directory

    db = SessionLocal()
    try:
        print(f"[bootstrap] ingesting knowledge documents from {seed_dir}")
        result = seed_documents_from_directory(db, Path(seed_dir))
        print(f"[bootstrap] knowledge seed result: {result}")
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bootstrap the AWS PostgreSQL database for the service desk app.")
    parser.add_argument("--schema", action="store_true", help="Run schema SQL files.")
    parser.add_argument("--seed-sql", action="store_true", help="Run SQL seed files.")
    parser.add_argument("--seed-structured", action="store_true", help="Load structured CSV seed data.")
    parser.add_argument("--seed-knowledge", action="store_true", help="Ingest seed knowledge documents.")
    parser.add_argument(
        "--knowledge-seed-dir",
        default="data/knowledge_base/seed",
        help="Directory containing seed knowledge documents.",
    )
    args = parser.parse_args(argv)

    if not any([args.schema, args.seed_sql, args.seed_structured, args.seed_knowledge]):
        args.schema = True
        args.seed_sql = True
        args.seed_structured = True
        args.seed_knowledge = True

    if args.schema:
        run_sql_files(SCHEMA_FILES)
    if args.seed_sql:
        run_sql_files(SEED_SQL_FILES)
    if args.seed_structured:
        seed_structured_data()
    if args.seed_knowledge:
        seed_knowledge_base(args.knowledge_seed_dir)

    print("[bootstrap] complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
