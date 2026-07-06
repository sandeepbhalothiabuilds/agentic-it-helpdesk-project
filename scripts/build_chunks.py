from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.db.session import SessionLocal
from app.backend.services.knowledge_base_service import (
    get_knowledge_base_snapshot,
    refresh_knowledge_base,
)


def _print_snapshot(label: str, snapshot: dict[str, Any]) -> None:
    summary = snapshot.get("summary", {}) if isinstance(snapshot, dict) else {}
    print(f"{label}:")
    print(
        "  active_documents={active_documents} active_revisions={active_revisions} active_chunks={active_chunks} total_chunks={total_chunks}".format(
            active_documents=summary.get("active_documents", 0),
            active_revisions=summary.get("active_revisions", 0),
            active_chunks=summary.get("active_chunks", 0),
            total_chunks=summary.get("total_chunks", summary.get("all_chunks", 0)),
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or rebuild the active knowledge base chunk index."
    )
    parser.add_argument(
        "--chunk-limit",
        type=int,
        default=50,
        help="Number of recent chunks to include in the printed snapshot.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the current snapshot without rebuilding the vector store.",
    )
    args = parser.parse_args(argv)

    with SessionLocal() as db:
        before = get_knowledge_base_snapshot(db, chunk_limit=args.chunk_limit)
        _print_snapshot("Before", before)

        if args.dry_run:
            return 0

        result = refresh_knowledge_base(db)
        print("Refresh result:")
        print(result)

        after = get_knowledge_base_snapshot(db, chunk_limit=args.chunk_limit)
        _print_snapshot("After", after)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
