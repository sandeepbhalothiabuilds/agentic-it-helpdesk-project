from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.db.session import SessionLocal
from app.backend.services.admin_service import get_system_status
from app.backend.services.preflight_service import run_preflight_checks


def main() -> int:
    db = SessionLocal()
    try:
        preflight = run_preflight_checks(db)
        system_status = get_system_status(db)
        payload = {
            "ok": bool(preflight.get("ready")) and bool(system_status.get("ready")),
            "preflight": preflight,
            "system_status": {
                "status": system_status.get("status"),
                "ready": system_status.get("ready"),
                "generated_at": system_status.get("generated_at"),
                "counts": system_status.get("counts"),
                "config": system_status.get("config"),
                "proof": system_status.get("proof"),
            },
        }
    finally:
        db.close()

    print(json.dumps(payload, indent=2, default=str))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
