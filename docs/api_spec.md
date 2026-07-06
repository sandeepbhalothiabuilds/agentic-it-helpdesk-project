# API Specification

Base URL locally: `http://localhost:8000`

## Health and operations

### `GET /health`
Returns lightweight service health.

### `GET /live` and `GET /health/live`
Container liveness check.

### `GET /ready` and `GET /health/ready`
Runs database/config/preflight readiness checks. Returns HTTP 503 when not ready.

### `GET /version`
Returns service version metadata.

### `GET /metrics`
Returns JSON operational counters.

### `GET /admin/status`
Returns system status, redacted config, health checks, counts, warnings, and proof metadata.

## Chat and workflow

### `POST /chat`
Request:

```json
{
  "employee_id": "E10231",
  "message": "reset my password",
  "confirm": false,
  "request_id": null
}
```

Response statuses include `needs_clarification`, `awaiting_confirmation`, `completed`, and `failed`.

### `GET /workflow/sessions`
Query parameters: `employee_id`, `status`, `limit`.

### `GET /workflow/history/{request_id}`
Returns summary, session, workflow events, and retrieval logs for one request.

## Retrieval

### `POST /retrieve`
Request:

```json
{
  "query": "password reset policy",
  "workflow": "password_reset",
  "top_k": 5,
  "min_score": 0.0,
  "candidate_limit": 500,
  "include_general": true
}
```

Returns ranked chunks with score components, matched terms, confidence, strategy, and citations.

## Knowledge base

### `GET /knowledge-base/summary`
Overview plus documents, revisions, workflow breakdown, and chunks.

### `POST /knowledge-base/upload`
Multipart form with `file`, `workflow`, `uploaded_by`, and `source_document_name`.

### `POST /knowledge-base/refresh`
Rebuilds active chunks from active knowledge document revisions.

### `GET /knowledge-base/revisions`
Returns revision history with filters.

### `GET /knowledge-base/search`
Searches documents, revisions, and chunks.

### `GET /knowledge-base/documents/{document_id}`
Returns one revision.

### `GET /knowledge-base/documents/{document_id}/download`
Downloads the stored source file.

### `PATCH /knowledge-base/documents/{document_id}`
Updates metadata such as workflow and owner.

### `POST /knowledge-base/documents/{document_id}/activate`
Makes a revision active and syncs chunk activity.

### `POST /knowledge-base/documents/{document_id}/deactivate`
Deactivates a revision and promotes the previous revision when appropriate.

## Tickets and audit

### `GET /tickets`
Filters: `employee_id`, `status`, `priority`, `category`, `active_only`, `limit`.

### `GET /audit`
Filters: `request_id`, `stage`, `status`, `active_only`, `limit`.
