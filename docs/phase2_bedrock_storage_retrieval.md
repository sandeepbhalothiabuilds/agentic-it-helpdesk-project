# Phase 2 Batch 2: Bedrock Embeddings, S3 Knowledge Storage, and Bedrock Knowledge Bases

This batch moves the project from an AWS-hosted application to an AWS-native knowledge and retrieval stack while preserving the existing PostgreSQL retrieval path as a safe fallback.

## Goals

1. Use Amazon Bedrock for document embeddings during upload and refresh.
2. Store uploaded/revisioned knowledge-base files in Amazon S3 instead of container-local disk.
3. Allow runtime retrieval through Amazon Bedrock Knowledge Bases.
4. Keep the existing `case4.document_chunks` PostgreSQL vector/search path available for rollback and fallback.
5. Surface storage, embedding, and retrieval provider status in `/admin/status`, `/ready`, and the System Admin UI.

## New provider switches

```bash
# Embeddings
EMBEDDING_PROVIDER=bedrock
EMBEDDING_FALLBACK_PROVIDER=huggingface
AWS_REGION=us-east-1
BEDROCK_EMBEDDING_MODEL_ID=amazon.titan-embed-text-v2:0
BEDROCK_EMBEDDING_DIMENSIONS=1024
BEDROCK_EMBEDDING_NORMALIZE=true

# Knowledge file storage
KB_STORAGE_BACKEND=s3
KB_S3_BUCKET=<your-knowledge-bucket>
KB_S3_PREFIX=knowledge-base/uploads
KB_S3_VALIDATE=false
KB_S3_SSE=aws:kms
KB_S3_KMS_KEY_ID=<optional-kms-key-id>

# Retrieval
RETRIEVAL_PROVIDER=bedrock_kb
RETRIEVAL_FALLBACK_TO_DB=true
BEDROCK_KNOWLEDGE_BASE_ID=<your-bedrock-kb-id>
BEDROCK_KB_DATA_SOURCE_ID=<optional-data-source-id>
BEDROCK_KB_NUMBER_OF_RESULTS=5
BEDROCK_KB_SEARCH_TYPE=HYBRID
```

## Storage behavior

When `KB_STORAGE_BACKEND=local`, uploaded files continue to be written under `KB_STORAGE_ROOT`.

When `KB_STORAGE_BACKEND=s3`, uploaded files are written to:

```text
s3://<KB_S3_BUCKET>/<KB_S3_PREFIX>/<logical-document>/rev_<revision>/<original-filename>
```

The database registry remains the source of truth:

- `case4.knowledge_documents.storage_type = 's3'`
- `case4.knowledge_documents.storage_path = 's3://bucket/key'`
- chunk metadata also includes `storage_type` and `storage_path`

The download endpoint remains compatible with both backends:

```text
GET /knowledge-base/documents/{document_id}/download
```

## Embedding behavior

When `EMBEDDING_PROVIDER=bedrock`, document ingestion and vector refresh call Bedrock Runtime `InvokeModel` with the configured embedding model. For Titan Text Embeddings V2, the request includes:

```json
{
  "inputText": "...",
  "dimensions": 1024,
  "normalize": true
}
```

If the Bedrock provider fails and `EMBEDDING_FALLBACK_PROVIDER` is not `none`, ingestion falls back to the configured fallback provider.

## Retrieval behavior

When `RETRIEVAL_PROVIDER=db`, the app uses the existing hybrid PostgreSQL path:

- semantic score from chunk embeddings,
- lexical keyword score,
- phrase boost,
- workflow boost,
- deterministic lexical fallback.

When `RETRIEVAL_PROVIDER=bedrock_kb`, the app calls Amazon Bedrock Knowledge Bases `Retrieve` and formats the results into the same evidence shape used by the chat UI and audit trail.

If Bedrock Knowledge Bases fails and `RETRIEVAL_FALLBACK_TO_DB=true`, the app falls back to PostgreSQL retrieval and adds:

```json
{
  "fallback_used": true,
  "requested_retrieval_provider": "bedrock_kb",
  "fallback_reason": "..."
}
```

## Admin / preflight behavior

The operational endpoints now include status for:

- LLM provider,
- embedding provider,
- retrieval provider,
- Bedrock Knowledge Base configuration,
- knowledge storage backend,
- S3 bucket configuration and optional validation,
- AgentCore runtime configuration.

Useful endpoints:

```text
GET /admin/status
GET /ready
GET /architecture/summary
```

## IAM permissions

Scope these permissions to specific model ARNs, bucket ARNs, and knowledge base ARNs before production.

### Bedrock embeddings

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:InvokeModel"],
  "Resource": "*"
}
```

### S3 knowledge storage

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:GetObject",
    "s3:HeadObject"
  ],
  "Resource": "arn:aws:s3:::<your-knowledge-bucket>/knowledge-base/uploads/*"
}
```

If `KB_S3_VALIDATE=true`, also allow:

```json
{
  "Effect": "Allow",
  "Action": ["s3:ListBucket"],
  "Resource": "arn:aws:s3:::<your-knowledge-bucket>"
}
```

If using SSE-KMS, add the relevant KMS permissions for the selected key.

### Bedrock Knowledge Bases retrieval

```json
{
  "Effect": "Allow",
  "Action": ["bedrock:Retrieve"],
  "Resource": "*"
}
```

## Recommended rollout

1. Deploy with `EMBEDDING_PROVIDER=huggingface`, `KB_STORAGE_BACKEND=local`, and `RETRIEVAL_PROVIDER=db` to confirm no regression.
2. Set `KB_STORAGE_BACKEND=s3` and upload a small test document.
3. Confirm the revision registry stores `storage_type=s3` and an `s3://...` storage path.
4. Enable `EMBEDDING_PROVIDER=bedrock` and upload/refresh one test document.
5. Confirm `/admin/status` shows the Bedrock embedding provider as configured.
6. Create/configure the Bedrock Knowledge Base in AWS and sync its data source.
7. Set `RETRIEVAL_PROVIDER=bedrock_kb` with `RETRIEVAL_FALLBACK_TO_DB=true`.
8. Submit a chat request and confirm evidence cards show `retrieval_strategy=bedrock_kb`.
9. Disable fallback only after retrieval quality, IAM, and latency are validated.

## Rollback

Rollback is environment-variable-only:

```bash
EMBEDDING_PROVIDER=huggingface
KB_STORAGE_BACKEND=local
RETRIEVAL_PROVIDER=db
RETRIEVAL_FALLBACK_TO_DB=true
```

The document registry and PostgreSQL retrieval path are preserved during the transition.
