# Pre-AWS Runbook

This runbook captures the final checks before deploying the Agentic IT Service Desk to AWS.

## Required AWS-side decisions

- Compute target: ECS/Fargate, EC2, App Runner, or EKS.
- Database: RDS PostgreSQL using schema `case4`.
- Secrets: AWS Secrets Manager or SSM Parameter Store.
- Upload storage: persistent EFS volume or S3-backed replacement for `KB_STORAGE_ROOT`.
- Network: VPC/subnets/security groups, ALB, TLS certificate, frontend/backend routing.
- Observability: CloudWatch logs, alarms, metrics scraping if needed.

## Required configuration

Set these values through the ECS task definition, App Runner configuration, or another AWS runtime environment:

- `DATABASE_URL` — preferred full PostgreSQL SQLAlchemy URL.
- `MISTRAL_API_KEY` — required when `MISTRAL_DISABLE=0`.
- `MISTRAL_MODEL` — default `mistral-small-latest`.
- `EMBEDDING_PROVIDER` — `huggingface` or `ollama`.
- `EMBEDDING_MODEL` — embedding model name.
- `OLLAMA_URL` — required when using Ollama embeddings.
- `CORS_ORIGINS` — deployed Streamlit origin.
- `TRUSTED_HOSTS` — backend hostnames / ALB DNS names.
- `API_KEY_REQUIRED=true` and `BACKEND_API_KEY` — recommended for shared/prod environments.
- `KB_STORAGE_ROOT` — persistent knowledge-base upload path.
- `ALLOW_SQLITE_FALLBACK=false` — recommended outside local/test environments.

Never commit `.env` or real secret values. The repository should only contain `.env.example` placeholders.

## Local validation before AWS

```bash
python -m compileall app scripts tests
pytest -q
python scripts/preflight_check.py
```

`pytest -q` passes in this package with 26 tests passing and 3 skipped tests in the lightweight environment.

## Docker validation

```bash
docker compose build
docker compose up
curl http://localhost:8000/live
curl http://localhost:8000/ready
curl http://localhost:8501/_stcore/health
```

The backend container includes `/health` health checks, and the frontend waits for a healthy backend.

## Security posture before AWS

- API-key protection is optional locally and can be required with `API_KEY_REQUIRED=true`.
- The frontend sends `BACKEND_API_KEY` as `X-API-Key` when configured.
- The backend adds request IDs and response security headers.
- Admin status and preflight responses expose only redacted database URLs.
- `.gitignore` and `.dockerignore` exclude local secrets and uploaded knowledge-base files.
- `.env.example` has placeholders only.

## AWS deployment steps still pending

1. Build and push backend/frontend images to ECR.
2. Provision RDS PostgreSQL.
3. Apply schema SQL files in `app/database/schema/`.
4. Load structured seed data with `scripts/load_structured_data.py`.
5. Seed/index knowledge documents with `scripts/ingest_documents.py`.
6. Configure secrets and environment variables.
7. Deploy backend and frontend services.
8. Configure ALB/TLS/CORS/trusted hosts.
9. Attach persistent knowledge-base storage.
10. Run `scripts/preflight_check.py` inside the deployed backend task.
11. Execute manual validation from `docs/final_validation.md`.
