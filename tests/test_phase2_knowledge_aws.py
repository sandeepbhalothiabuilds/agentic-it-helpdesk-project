from __future__ import annotations

import json
from types import SimpleNamespace

from app.backend.rag import bedrock_kb_service, embedding_service
from app.backend.services import retrieval_service
from app.backend.storage import s3_storage


class DummyBody:
    def __init__(self, payload: dict):
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self):
        return self.payload


class DummyBedrockEmbeddingClient:
    def __init__(self):
        self.request = None

    def invoke_model(self, **kwargs):
        self.request = kwargs
        return {"body": DummyBody({"embedding": [0.1, 0.2, 0.3]})}


class DummyS3Client:
    def __init__(self):
        self.objects: dict[tuple[str, str], bytes] = {}
        self.head_calls: list[tuple[str, str]] = []
        self.last_put_kwargs = None

    def put_object(self, **kwargs):
        self.last_put_kwargs = kwargs
        self.objects[(kwargs["Bucket"], kwargs["Key"])] = kwargs["Body"]
        return {"ETag": '"abc"'}

    def get_object(self, **kwargs):
        return {"Body": DummyRaw(self.objects[(kwargs["Bucket"], kwargs["Key"])])}

    def head_object(self, **kwargs):
        self.head_calls.append((kwargs["Bucket"], kwargs["Key"]))
        return {"ContentLength": len(self.objects[(kwargs["Bucket"], kwargs["Key"])]), "ContentType": "text/plain", "ETag": '"abc"', "Metadata": {}}

    def generate_presigned_url(self, **kwargs):
        return f"https://example.com/{kwargs['Params']['Bucket']}/{kwargs['Params']['Key']}"


class DummyRaw:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self):
        return self.payload


class DummyBedrockKbClient:
    def __init__(self):
        self.request = None

    def retrieve(self, **kwargs):
        self.request = kwargs
        return {
            "retrievalResults": [
                {
                    "content": {"text": "Reset password after identity verification."},
                    "score": 0.91,
                    "metadata": {"source_document": "password_runbook"},
                    "location": {"type": "S3", "s3Location": {"uri": "s3://kb/password.pdf"}},
                }
            ]
        }


def test_bedrock_embedding_provider_invokes_model(monkeypatch):
    dummy_client = DummyBedrockEmbeddingClient()
    monkeypatch.setattr(embedding_service.settings, "embedding_provider", "bedrock")
    monkeypatch.setattr(embedding_service.settings, "embedding_fallback_provider", "none")
    monkeypatch.setattr(embedding_service.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(embedding_service.settings, "bedrock_embedding_model_id", "amazon.titan-embed-text-v2:0")
    monkeypatch.setattr(embedding_service.settings, "bedrock_embedding_dimensions", 512)
    monkeypatch.setattr(embedding_service.settings, "bedrock_embedding_normalize", "1")
    monkeypatch.setattr(embedding_service, "_bedrock_runtime_client", lambda: dummy_client)

    vector = embedding_service.embed_text("hello world")

    assert vector == [0.1, 0.2, 0.3]
    assert dummy_client.request["modelId"] == "amazon.titan-embed-text-v2:0"
    body = json.loads(dummy_client.request["body"].decode())
    assert body["inputText"] == "hello world"
    assert body["dimensions"] == 512
    assert body["normalize"] is True


def test_s3_storage_put_get_and_presign(monkeypatch):
    dummy_client = DummyS3Client()
    monkeypatch.setattr(s3_storage.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(s3_storage.settings, "kb_s3_bucket", "kb-bucket")
    monkeypatch.setattr(s3_storage.settings, "kb_s3_prefix", "knowledge-base/uploads")
    monkeypatch.setattr(s3_storage.settings, "kb_s3_sse", "aws:kms")
    monkeypatch.setattr(s3_storage.settings, "kb_s3_kms_key_id", "alias/kb-key")
    monkeypatch.setattr(s3_storage, "_client", lambda: dummy_client)

    key = s3_storage.build_s3_key("runbook", "rev_001", "runbook.txt")
    ref = s3_storage.put_object_bytes(content=b"hello", key=key, content_type="text/plain")

    assert ref.uri == "s3://kb-bucket/knowledge-base/uploads/runbook/rev_001/runbook.txt"
    assert dummy_client.last_put_kwargs["ServerSideEncryption"] == "aws:kms"
    assert dummy_client.last_put_kwargs["SSEKMSKeyId"] == "alias/kb-key"
    assert dummy_client.last_put_kwargs["Metadata"]["sha256"]
    assert s3_storage.get_object_bytes(ref.uri) == b"hello"
    assert s3_storage.object_exists(ref.uri) is True
    assert s3_storage.presign_get_url(ref.uri).startswith("https://example.com/kb-bucket/")


def test_bedrock_kb_retrieve_formats_results(monkeypatch):
    dummy_client = DummyBedrockKbClient()
    monkeypatch.setattr(bedrock_kb_service.settings, "aws_region", "us-east-1")
    monkeypatch.setattr(bedrock_kb_service.settings, "bedrock_knowledge_base_id", "KB123")
    monkeypatch.setattr(bedrock_kb_service.settings, "bedrock_kb_search_type", "HYBRID")
    monkeypatch.setattr(bedrock_kb_service, "_client", lambda: dummy_client)

    payload = bedrock_kb_service.retrieve_knowledge_base(query="reset password", workflow="password_reset", top_k=2)

    assert payload["source"] == "bedrock_kb"
    assert payload["knowledge_base_id"] == "KB123"
    assert payload["results"][0]["source_document"] == "password_runbook"
    assert payload["results"][0]["retrieval_strategy"] == "bedrock_kb"
    assert dummy_client.request["retrievalConfiguration"]["vectorSearchConfiguration"]["overrideSearchType"] == "HYBRID"


def test_retrieval_service_routes_to_bedrock_kb(monkeypatch):
    monkeypatch.setattr(retrieval_service.settings, "retrieval_provider", "bedrock_kb")
    monkeypatch.setattr(retrieval_service.settings, "retrieval_fallback_to_db", "1")
    monkeypatch.setattr(
        retrieval_service.bedrock_kb_service,
        "retrieve_knowledge_base",
        lambda **kwargs: {
            "query": kwargs["query"],
            "workflow": kwargs["workflow"],
            "results": [{"chunk_id": "bedrock-kb-1", "score": 0.9}],
            "source": "bedrock_kb",
            "retrieval_strategy": "bedrock_kb",
            "result_count": 1,
        },
    )

    payload = retrieval_service.search_knowledge("reset password", "password_reset", top_k=1)

    assert payload["source"] == "bedrock_kb"
    assert payload["fallback_used"] is False
    assert payload["results"][0]["chunk_id"] == "bedrock-kb-1"
