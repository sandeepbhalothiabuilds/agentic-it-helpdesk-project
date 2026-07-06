from __future__ import annotations

from app.backend.config import settings


def main() -> int:
    try:
        import psycopg2
    except ImportError:
        print("psycopg2 is not installed; skipping database smoke test.")
        return 0

    conn = psycopg2.connect(
        host="service-desk-db.cuzi44wo4n90.us-east-1.rds.amazonaws.com",
        database="postgres",
        user="service_desk",
        password=settings.db_password,
        port=5432,
        sslmode="require",
    )
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            print("DB connection OK, SELECT 1 ->", cur.fetchone())
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
