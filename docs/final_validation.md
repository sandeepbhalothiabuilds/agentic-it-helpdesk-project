# Final Validation

Run these checks before AWS deployment:

```bash
python -m compileall app scripts tests
pytest -q
python scripts/preflight_check.py
```

Expected test status in this package:

```text
26 passed, 3 skipped
```

The skipped tests are acceptable in lightweight environments where optional runtime components are absent.

## Manual local validation

1. Start backend.
2. Open `/health`, `/ready`, `/metrics`, and `/admin/status`.
3. Start Streamlit.
4. Submit an ambiguous request and verify clarification.
5. Submit a password reset request and verify confirmation appears.
6. Confirm the request and verify execution, ticket creation, audit logs, workflow events, and evidence cards.
7. Upload a test document to the Knowledge Base page.
8. Refresh the vector store.
9. Search the knowledge base and retrieval endpoint.
10. Verify Dashboard, Tickets, Audit, Workflow History, Architecture, and System Admin pages render without oversized or unknown status cards.

## AWS-only work remaining

- Provision network, database, compute, and storage.
- Apply schema files and seed data.
- Configure Secrets Manager / Parameter Store.
- Push images to ECR and deploy backend/frontend.
- Configure ALB/TLS/CORS/security groups.
- Attach persistent storage for knowledge uploads or replace local storage with S3.
- Run preflight inside the deployed backend task.
