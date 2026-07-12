from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import urlparse

from app.backend.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class S3ObjectRef:
    bucket: str
    key: str

    @property
    def uri(self) -> str:
        return build_s3_uri(self.bucket, self.key)


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
        from botocore.exceptions import ClientError  # type: ignore
    except Exception as exc:  # pragma: no cover - dependency failure is environment-specific
        raise RuntimeError("boto3 and botocore are required for S3 knowledge-base storage.") from exc
    return boto3, Config, ClientError


def _session():
    boto3, _, _ = _load_boto3()
    profile = (settings.aws_profile or "").strip()
    if profile:
        return boto3.Session(profile_name=profile, region_name=settings.aws_region)
    return boto3.Session(region_name=settings.aws_region)


def _client():
    _, Config, _ = _load_boto3()
    config = Config(
        connect_timeout=int(getattr(settings, "bedrock_request_timeout_seconds", 60) or 60),
        read_timeout=int(getattr(settings, "bedrock_request_timeout_seconds", 60) or 60),
        retries={"max_attempts": 3, "mode": "standard"},
    )
    return _session().client("s3", region_name=settings.aws_region, config=config)


def _clean_part(value: str) -> str:
    cleaned = (value or "").strip().replace("\\", "/")
    cleaned = "/".join(part for part in cleaned.split("/") if part not in {"", "."})
    return cleaned.strip("/")


def normalize_prefix(prefix: str | None = None) -> str:
    return _clean_part(prefix if prefix is not None else settings.kb_s3_prefix)


def build_s3_key(*parts: str, prefix: str | None = None) -> str:
    clean_parts = [_clean_part(part) for part in parts if _clean_part(part)]
    selected_prefix = normalize_prefix(prefix)
    all_parts = ([selected_prefix] if selected_prefix else []) + clean_parts
    return str(PurePosixPath(*all_parts)) if all_parts else ""


def build_s3_uri(bucket: str, key: str) -> str:
    clean_bucket = (bucket or "").strip()
    clean_key = _clean_part(key)
    if not clean_bucket or not clean_key:
        raise ValueError("Both S3 bucket and key are required.")
    return f"s3://{clean_bucket}/{clean_key}"


def parse_s3_uri(value: str) -> S3ObjectRef:
    text = (value or "").strip()
    if not text.startswith("s3://"):
        bucket = (settings.kb_s3_bucket or "").strip()
        key = _clean_part(text)
        if not bucket or not key:
            raise ValueError(f"Invalid S3 URI or key: {value!r}")
        return S3ObjectRef(bucket=bucket, key=key)

    parsed = urlparse(text)
    bucket = parsed.netloc.strip()
    key = _clean_part(parsed.path)
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {value!r}")
    return S3ObjectRef(bucket=bucket, key=key)


def put_object_bytes(
    *,
    content: bytes,
    key: str,
    bucket: str | None = None,
    content_type: str | None = None,
    metadata: dict[str, str] | None = None,
) -> S3ObjectRef:
    selected_bucket = (bucket or settings.kb_s3_bucket or "").strip()
    clean_key = _clean_part(key)
    if not selected_bucket:
        raise ValueError("KB_S3_BUCKET is required when KB_STORAGE_BACKEND=s3.")
    if not clean_key:
        raise ValueError("A non-empty S3 object key is required.")

    extra: dict[str, Any] = {}
    if content_type:
        extra["ContentType"] = content_type
    if metadata:
        extra["Metadata"] = {str(k): str(v) for k, v in metadata.items() if v is not None}

    extra["Metadata"] = {
        **extra.get("Metadata", {}),
        "sha256": hashlib.sha256(content).hexdigest(),
    }

    sse = (getattr(settings, "kb_s3_sse", "") or "").strip()
    kms_key_id = (getattr(settings, "kb_s3_kms_key_id", "") or "").strip()
    if sse:
        extra["ServerSideEncryption"] = sse
    if kms_key_id:
        extra["SSEKMSKeyId"] = kms_key_id

    logger.info("Uploading knowledge document to S3", extra={"bucket": selected_bucket, "key": clean_key})
    _client().put_object(Bucket=selected_bucket, Key=clean_key, Body=content, **extra)
    return S3ObjectRef(bucket=selected_bucket, key=clean_key)


def get_object_bytes(uri_or_key: str, *, bucket: str | None = None) -> bytes:
    ref = parse_s3_uri(uri_or_key) if bucket is None else S3ObjectRef(bucket=bucket, key=_clean_part(uri_or_key))
    response = _client().get_object(Bucket=ref.bucket, Key=ref.key)
    return response["Body"].read()


def object_exists(uri_or_key: str, *, bucket: str | None = None) -> bool:
    ref = parse_s3_uri(uri_or_key) if bucket is None else S3ObjectRef(bucket=bucket, key=_clean_part(uri_or_key))
    _, _, ClientError = _load_boto3()
    try:
        _client().head_object(Bucket=ref.bucket, Key=ref.key)
        return True
    except ClientError as exc:
        status_code = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        error_code = str(exc.response.get("Error", {}).get("Code") or "")
        if status_code == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
            return False
        raise


def get_object_info(uri_or_key: str, *, bucket: str | None = None) -> dict[str, Any]:
    ref = parse_s3_uri(uri_or_key) if bucket is None else S3ObjectRef(bucket=bucket, key=_clean_part(uri_or_key))
    _, _, ClientError = _load_boto3()
    try:
        response = _client().head_object(Bucket=ref.bucket, Key=ref.key)
        return {
            "exists": True,
            "bucket": ref.bucket,
            "key": ref.key,
            "uri": ref.uri,
            "size": response.get("ContentLength"),
            "content_type": response.get("ContentType"),
            "etag": str(response.get("ETag") or "").strip('"'),
            "metadata": response.get("Metadata", {}),
            "last_modified": response.get("LastModified"),
        }
    except ClientError as exc:
        status_code = int(exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") or 0)
        error_code = str(exc.response.get("Error", {}).get("Code") or "")
        if status_code == 404 or error_code in {"404", "NoSuchKey", "NotFound"}:
            return {"exists": False, "bucket": ref.bucket, "key": ref.key, "uri": ref.uri}
        raise


def presign_get_url(uri_or_key: str, *, bucket: str | None = None, expires_in: int | None = None) -> str:
    ref = parse_s3_uri(uri_or_key) if bucket is None else S3ObjectRef(bucket=bucket, key=_clean_part(uri_or_key))
    seconds = int(expires_in or settings.kb_s3_presign_seconds or 900)
    return _client().generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": ref.bucket, "Key": ref.key},
        ExpiresIn=seconds,
    )


def get_storage_status(*, validate: bool | None = None) -> dict[str, Any]:
    backend = settings.kb_storage_backend_normalized
    if backend != "s3":
        root = getattr(settings, "kb_storage_root", "data/knowledge_base/uploads")
        return {
            "ok": True,
            "configured": True,
            "provider": "local",
            "path": root,
            "message": "Local knowledge-base storage is selected.",
            "validated": False,
        }

    bucket = (settings.kb_s3_bucket or "").strip()
    configured = bool(bucket and (settings.aws_region or "").strip())
    status = {
        "ok": configured,
        "configured": configured,
        "provider": "s3",
        "bucket_set": bool(bucket),
        "bucket": bucket if bucket else None,
        "prefix": normalize_prefix(),
        "region": settings.aws_region,
        "validated": False,
        "message": "S3 knowledge-base storage is configured." if configured else "Set AWS_REGION and KB_S3_BUCKET when KB_STORAGE_BACKEND=s3.",
        "sse": getattr(settings, "kb_s3_sse", "") or None,
        "kms_key_set": bool(getattr(settings, "kb_s3_kms_key_id", "") or ""),
    }
    should_validate = settings.kb_s3_validate_enabled if validate is None else bool(validate)
    if not configured or not should_validate:
        return status

    try:
        _client().head_bucket(Bucket=bucket)
        status.update({"ok": True, "validated": True, "message": "S3 bucket probe succeeded."})
    except Exception as exc:
        status.update({"ok": False, "validated": True, "message": str(exc)})
    return status
