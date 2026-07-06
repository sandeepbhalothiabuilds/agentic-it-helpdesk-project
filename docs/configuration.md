# Configuration

The application reads environment variables through `app/backend/config.py` and `.env` during local development.

## Required before AWS

- `DATABASE_URL` or `DB_PASSWORD` plus DB host/user/name settings.
- `MISTRAL_API_KEY` when `MISTRAL_DISABLE=0`.
- `CORS_ORIGINS` with the deployed frontend origin.
- `TRUSTED_HOSTS` with backend hostnames.
- `API_KEY_REQUIRED=true` and `BACKEND_API_KEY` for shared/prod environments.
- Persistent `KB_STORAGE_ROOT` path.

## Core variables

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | Runtime environment label. |
| `APP_VERSION` | Version shown in health/admin payloads. |
| `LOG_LEVEL` | Python log level. |
| `DATABASE_URL` | Preferred full SQLAlchemy DB URL. |
| `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_SSLMODE` | DB parts used when `DATABASE_URL` is absent. |
| `ALLOW_SQLITE_FALLBACK` / `ENABLE_SQLITE_FALLBACK` | Local/test fallback only. Disable in production. |
| `MISTRAL_API_KEY` | Mistral credential. |
| `MISTRAL_MODEL` | Chat/completion model. |
| `MISTRAL_DISABLE` | Set `1` to force local fallback responses. |
| `EMBEDDING_PROVIDER` | `huggingface` or `ollama`. |
| `EMBEDDING_MODEL` | Hugging Face embedding model. |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Ollama embedding configuration. |
| `CORS_ORIGINS` | Comma-separated frontend origins. |
| `TRUSTED_HOSTS` | Comma-separated backend hostnames. |
| `API_KEY_REQUIRED` | Enables backend API-key protection. |
| `BACKEND_API_KEY` | Shared API key used by frontend and backend. |
| `KB_STORAGE_ROOT` | Persistent upload root. |
| `MAX_UPLOAD_MB` | Upload limit configuration value. |

## Preflight

Run:

```bash
python scripts/preflight_check.py
```

The script checks configuration, storage writability, database reachability, required tables, and knowledge-base counts.
