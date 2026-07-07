from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.backend.db.session import SessionLocal

STRUCTURED_DATA_ROOT = Path(os.getenv("STRUCTURED_DATA_ROOT", "data/raw/structured"))

TABLES: list[tuple[str, str, str]] = [
    ("users.csv", "users", "user_id"),
    ("devices.csv", "devices", "device_id"),
    ("service_tickets.csv", "service_tickets", "ticket_id"),
    ("iam_accounts.csv", "iam_accounts", "user_id"),
    ("vpn_profiles.csv", "vpn_profiles", "user_id"),
    ("action_requests.csv", "action_requests", "request_id"),
    ("runbook_rules.csv", "runbook_rules", "rule_id"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _clean(value: Any, default: str = "") -> str:
    if value is None:
        return default
    text_value = str(value).strip()
    return text_value if text_value else default


def _parse_bool(value: Any, default: bool = False) -> bool:
    text_value = _clean(value).lower()
    if text_value in {"1", "true", "t", "yes", "y", "enabled", "active", "pass", "ok"}:
        return True
    if text_value in {"0", "false", "f", "no", "n", "disabled", "inactive", "fail"}:
        return False
    return default


def _parse_int(value: Any, default: int = 0) -> int:
    text_value = _clean(value)
    if not text_value:
        return default
    match = re.search(r"-?\d+", text_value)
    if not match:
        return default
    try:
        return int(match.group(0))
    except ValueError:
        return default


def _parse_datetime(value: Any) -> datetime:
    text_value = _clean(value)
    if not text_value:
        return _now()

    normalized = text_value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.combine(date.fromisoformat(normalized[:10]), datetime.min.time())

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_date(value: Any) -> date:
    text_value = _clean(value)
    if not text_value:
        return _now().date()
    return date.fromisoformat(text_value[:10])


def _normalize_user(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    return {
        "user_id": _clean(row.get("user_id")),
        "employee_id": _clean(row.get("employee_id")),
        "full_name": _clean(row.get("full_name")),
        "department": _clean(row.get("department")),
        "location": _clean(row.get("location")),
        "manager": _clean(row.get("manager")),
        "email": _clean(row.get("email")),
        "status": _clean(row.get("status"), "Active"),
        "identity_verification_level": _clean(row.get("identity_verification_level"), "Standard"),
        "created_at": now,
        "created_by": "structured_loader",
        "updated_at": now,
        "updated_by": "structured_loader",
        "is_active": True,
    }


def _normalize_device(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    encryption = _clean(row.get("encryption_status"), "Unknown")
    return {
        "device_id": _clean(row.get("device_id")),
        "user_id": _clean(row.get("user_id")),
        "device_name": _clean(row.get("device_name")),
        "device_type": _clean(row.get("device_type"), "Laptop"),
        "os": _clean(row.get("os"), "Unknown"),
        "encryption_status": encryption,
        "vpn_client_version": _clean(row.get("vpn_client_version"), "Unknown"),
        "last_seen": _parse_datetime(row.get("last_seen")),
        "compliance_status": _clean(row.get("compliance_status"), "Compliant" if encryption.lower() == "encrypted" else "Unknown"),
        "created_at": now,
        "created_by": "structured_loader",
        "updated_at": now,
        "updated_by": "structured_loader",
        "is_active": True,
    }


def _normalize_service_ticket(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    created_at = _parse_datetime(row.get("created_at"))
    return {
        "ticket_id": _clean(row.get("ticket_id")),
        "user_id": _clean(row.get("user_id")),
        "status": _clean(row.get("status"), "New"),
        "priority": _clean(row.get("priority"), "Medium"),
        "category": _clean(row.get("category"), "General"),
        "created_at": created_at,
        "last_updated": _parse_datetime(row.get("last_updated")) if _clean(row.get("last_updated")) else created_at,
        "assigned_group": _clean(row.get("assigned_group"), "Service Desk"),
        "summary": _clean(row.get("summary"), "Seed service ticket"),
        "created_by": "structured_loader",
        "updated_by": "structured_loader",
        "updated_at": now,
        "is_active": True,
    }


def _normalize_iam_account(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    locked_until_raw = _clean(row.get("locked_until"))
    return {
        "user_id": _clean(row.get("user_id")),
        "directory_account": _clean(row.get("directory_account")),
        "account_status": _clean(row.get("account_status"), "Active"),
        "mfa_enabled": _parse_bool(row.get("mfa_enabled"), default=True),
        "last_password_change": _parse_date(row.get("last_password_change")),
        "failed_login_count": _parse_int(row.get("failed_login_count"), default=0),
        "locked_until": _parse_datetime(locked_until_raw) if locked_until_raw else None,
        "created_at": now,
        "created_by": "structured_loader",
        "updated_at": now,
        "updated_by": "structured_loader",
        "is_active": True,
    }


def _normalize_vpn_profile(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    return {
        "user_id": _clean(row.get("user_id")),
        "vpn_status": _clean(row.get("vpn_status"), "Enabled"),
        "profile_name": _clean(row.get("profile_name"), "Corp-Standard"),
        "last_successful_login": _parse_datetime(row.get("last_successful_login")),
        "certificate_status": _clean(row.get("certificate_status"), "Valid"),
        "device_compliance": _clean(row.get("device_compliance"), "Pass"),
        "created_at": now,
        "created_by": "structured_loader",
        "updated_at": now,
        "updated_by": "structured_loader",
        "is_active": True,
    }


def _normalize_action_request(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    return {
        "request_id": _clean(row.get("request_id")),
        "user_id": _clean(row.get("user_id")),
        "action_type": _clean(row.get("action_type"), "General"),
        "requested_at": _parse_datetime(row.get("requested_at")),
        "confirmation_status": _clean(row.get("confirmation_status"), "Pending"),
        "execution_status": _clean(row.get("execution_status"), "Not Started"),
        "evidence_ref": _clean(row.get("evidence_ref"), "seed-data"),
        "outcome_notes": _clean(row.get("outcome_notes"), "Loaded from structured seed data."),
        "created_at": now,
        "created_by": "structured_loader",
        "updated_at": now,
        "updated_by": "structured_loader",
        "is_active": True,
    }


def _normalize_runbook_rule(row: dict[str, str]) -> dict[str, Any]:
    now = _now()
    return {
        "rule_id": _clean(row.get("rule_id")),
        "workflow": _clean(row.get("workflow"), "general"),
        "required_verification": _clean(row.get("required_verification"), "Standard"),
        "confirmation_required": _clean(row.get("confirmation_required"), "Yes"),
        "destructive_action_block": _clean(row.get("destructive_action_block"), "No"),
        "sla_target_minutes": _parse_int(row.get("sla_target_minutes") or row.get("sla_target"), default=60),
        "policy_version": _clean(row.get("policy_version"), "v1.0"),
        "owner_team": _clean(row.get("owner_team"), "Service Desk"),
        "created_at": now,
        "created_by": "structured_loader",
        "updated_at": now,
        "updated_by": "structured_loader",
        "is_active": True,
    }


NORMALIZERS: dict[str, Callable[[dict[str, str]], dict[str, Any]]] = {
    "users.csv": _normalize_user,
    "devices.csv": _normalize_device,
    "service_tickets.csv": _normalize_service_ticket,
    "iam_accounts.csv": _normalize_iam_account,
    "vpn_profiles.csv": _normalize_vpn_profile,
    "action_requests.csv": _normalize_action_request,
    "runbook_rules.csv": _normalize_runbook_rule,
}


def _upsert_statement(table: str, columns: Iterable[str], primary_key: str):
    cols = list(columns)
    insert_columns = ", ".join(cols)
    insert_values = ", ".join(f":{column}" for column in cols)
    update_values = ", ".join(f"{column} = EXCLUDED.{column}" for column in cols if column != primary_key)
    return text(
        f"""
        INSERT INTO case4.{table} ({insert_columns})
        VALUES ({insert_values})
        ON CONFLICT ({primary_key})
        DO UPDATE SET {update_values}
        """
    )


def seed_structured_data(db: Session | None = None, structured_root: Path | str = STRUCTURED_DATA_ROOT) -> dict[str, Any]:
    """Load structured CSV seed files into case4 tables using idempotent upserts."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    root = Path(structured_root)
    results: list[dict[str, Any]] = []
    loaded_rows = 0
    skipped_files = 0

    try:
        for filename, table, primary_key in TABLES:
            path = root / filename
            if not path.exists():
                skipped_files += 1
                results.append({"file": filename, "table": table, "status": "skipped", "reason": f"Missing file: {path}"})
                continue

            rows = _read_csv(path)
            if not rows:
                skipped_files += 1
                results.append({"file": filename, "table": table, "status": "skipped", "reason": "CSV file is empty"})
                continue

            normalizer = NORMALIZERS[filename]
            normalized_rows = [normalizer(row) for row in rows]
            normalized_rows = [row for row in normalized_rows if row.get(primary_key)]
            if not normalized_rows:
                skipped_files += 1
                results.append({"file": filename, "table": table, "status": "skipped", "reason": f"No rows with primary key {primary_key}"})
                continue

            statement = _upsert_statement(table=table, columns=normalized_rows[0].keys(), primary_key=primary_key)
            for row in normalized_rows:
                db.execute(statement, row)

            loaded_rows += len(normalized_rows)
            results.append({"file": filename, "table": table, "status": "loaded", "rows": len(normalized_rows)})

        db.commit()
        return {"status": "ok", "structured_root": str(root), "loaded_rows": loaded_rows, "skipped_files": skipped_files, "results": results}
    except Exception:
        db.rollback()
        raise
    finally:
        if close_db:
            db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load structured CSV seed data into PostgreSQL.")
    parser.add_argument("--structured-root", default=str(STRUCTURED_DATA_ROOT), help="Directory containing structured CSV seed files.")
    args = parser.parse_args(argv)

    result = seed_structured_data(structured_root=Path(args.structured_root))
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
