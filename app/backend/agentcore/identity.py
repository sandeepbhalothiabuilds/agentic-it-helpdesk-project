from __future__ import annotations

import logging
from typing import Any

from app.backend.config import settings

logger = logging.getLogger(__name__)

_TRUE = {"1", "true", "t", "yes", "y", "on", "enabled"}
_FALSE = {"0", "false", "f", "no", "n", "off", "disabled", ""}


def _truthy_setting(value: Any, default: bool = False) -> bool:
    text = str(value if value is not None else "").strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return default


def _load_boto3():
    try:
        import boto3  # type: ignore
        from botocore.config import Config  # type: ignore
    except Exception as exc:  # pragma: no cover - depends on AWS runtime packages
        raise RuntimeError("boto3 and botocore are required for Amazon Bedrock AgentCore Identity. Install boto3.") from exc
    return boto3, Config


def _session():
    boto3, _ = _load_boto3()
    profile = (getattr(settings, "aws_profile", "") or "").strip()
    region = getattr(settings, "aws_region", "us-east-1")
    if profile:
        return boto3.Session(profile_name=profile, region_name=region)
    return boto3.Session(region_name=region)


def _client():
    _, Config = _load_boto3()
    timeout = int(getattr(settings, "agentcore_timeout_seconds", 90) or 90)
    config = Config(
        connect_timeout=timeout,
        read_timeout=timeout,
        retries={"max_attempts": 2, "mode": "standard"},
    )
    return _session().client("bedrock-agentcore", region_name=getattr(settings, "aws_region", "us-east-1"), config=config)


def identity_enabled() -> bool:
    return bool(getattr(settings, "agentcore_identity_is_enabled", _truthy_setting(getattr(settings, "agentcore_identity_enabled", "0"))))


def _static_bearer_token() -> str:
    return (getattr(settings, "agentcore_gateway_bearer_token", "") or "").strip()


def _static_api_key() -> str:
    return (getattr(settings, "agentcore_gateway_api_key", "") or "").strip()


def _scopes() -> list[str]:
    if hasattr(settings, "agentcore_identity_scopes_list"):
        return list(settings.agentcore_identity_scopes_list)
    raw = str(getattr(settings, "agentcore_identity_scopes", "") or "").strip()
    return [item.strip() for item in raw.split(",") if item.strip()]


def identity_configured() -> bool:
    if not identity_enabled():
        return True
    if _static_bearer_token() or _static_api_key():
        return True
    return bool(
        (getattr(settings, "agentcore_identity_workload_token", "") or "").strip()
        and (getattr(settings, "agentcore_identity_resource_credential_provider_name", "") or "").strip()
        and _scopes()
    )


def get_identity_status() -> dict[str, Any]:
    enabled = identity_enabled()
    configured = identity_configured()
    status = {
        "ok": (not enabled) or configured,
        "enabled": enabled,
        "configured": configured,
        "static_bearer_token_set": bool(_static_bearer_token()),
        "static_api_key_set": bool(_static_api_key()),
        "managed_identity_configured": bool(
            (getattr(settings, "agentcore_identity_workload_token", "") or "").strip()
            and (getattr(settings, "agentcore_identity_resource_credential_provider_name", "") or "").strip()
            and _scopes()
        ),
        "resource_credential_provider_set": bool(getattr(settings, "agentcore_identity_resource_credential_provider_name", "")),
        "scopes": _scopes(),
        "oauth2_flow": getattr(settings, "agentcore_identity_oauth2_flow", "M2M"),
        "message": "AgentCore Identity is configured." if configured else "AgentCore Identity is enabled but missing credentials/provider/scopes.",
    }
    try:
        _load_boto3()
        status["boto3_available"] = True
    except Exception as exc:
        status["boto3_available"] = False
        if enabled and not (_static_bearer_token() or _static_api_key()):
            status["ok"] = False
            status["message"] = str(exc)
    return status


def get_resource_oauth2_token(*, session_id: str | None = None, force_authentication: bool | None = None) -> dict[str, Any]:
    """Return an AgentCore Identity OAuth2 token payload.

    Static gateway bearer/API-key credentials remain supported for transitional
    environments. When static credentials are present, this function returns a
    normalized local token payload without calling AgentCore Identity.
    """
    bearer = _static_bearer_token()
    if bearer:
        return {
            "ok": True,
            "source": "static_bearer_token",
            "accessToken": bearer.removeprefix("Bearer ").strip(),
            "sessionStatus": "STATIC",
        }

    api_key = _static_api_key()
    if api_key:
        return {
            "ok": True,
            "source": "static_api_key",
            "apiKey": api_key,
            "sessionStatus": "STATIC",
        }

    if not identity_enabled():
        return {"ok": True, "skipped": True, "source": "identity_disabled"}

    if not identity_configured():
        return {"ok": False, "error": "agentcore_identity_not_configured", **get_identity_status()}

    request: dict[str, Any] = {
        "workloadIdentityToken": getattr(settings, "agentcore_identity_workload_token", ""),
        "resourceCredentialProviderName": getattr(settings, "agentcore_identity_resource_credential_provider_name", ""),
        "scopes": _scopes(),
        "oauth2Flow": getattr(settings, "agentcore_identity_oauth2_flow", "M2M") or "M2M",
    }
    session_uri = session_id or getattr(settings, "agentcore_identity_session_uri", "")
    if session_uri:
        request["sessionUri"] = session_uri
    return_url = getattr(settings, "agentcore_identity_return_url", "")
    if return_url:
        request["resourceOauth2ReturnUrl"] = return_url
    if force_authentication is None:
        force_authentication = bool(getattr(settings, "agentcore_identity_force_authentication_enabled", False))
    request["forceAuthentication"] = bool(force_authentication)

    try:
        response = _client().get_resource_oauth2_token(**request)
        return {
            "ok": bool(response.get("accessToken") or response.get("authorizationUrl")),
            "source": "agentcore_identity",
            "accessToken": response.get("accessToken"),
            "authorizationUrl": response.get("authorizationUrl"),
            "sessionUri": response.get("sessionUri"),
            "sessionStatus": response.get("sessionStatus"),
            "response_metadata": response.get("ResponseMetadata", {}),
        }
    except Exception as exc:
        logger.warning("AgentCore Identity token request failed", extra={"event": "agentcore_identity_error"}, exc_info=True)
        return {"ok": False, "source": "agentcore_identity", "error": str(exc)}


def auth_headers(*, session_id: str | None = None) -> dict[str, str]:
    """Return gateway authorization headers from static credentials or AgentCore Identity."""
    headers: dict[str, str] = {}

    bearer = _static_bearer_token()
    if bearer:
        header_name = str(getattr(settings, "agentcore_gateway_auth_header", "Authorization") or "Authorization")
        headers[header_name] = bearer if bearer.lower().startswith("bearer ") else f"Bearer {bearer}"

    api_key = _static_api_key()
    if api_key:
        header_name = str(getattr(settings, "agentcore_gateway_api_key_header", "X-API-Key") or "X-API-Key")
        headers[header_name] = api_key

    if headers:
        return headers

    token_payload = get_resource_oauth2_token(session_id=session_id)
    if not token_payload.get("ok"):
        return {}

    if token_payload.get("apiKey"):
        header_name = str(getattr(settings, "agentcore_gateway_api_key_header", "X-API-Key") or "X-API-Key")
        return {header_name: str(token_payload["apiKey"])}

    access_token = token_payload.get("accessToken")
    if access_token:
        header_name = str(getattr(settings, "agentcore_gateway_auth_header", "Authorization") or "Authorization")
        token_text = str(access_token)
        return {header_name: token_text if token_text.lower().startswith("bearer ") else f"Bearer {token_text}"}

    return {}
