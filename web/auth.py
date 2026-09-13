"""
API key authentication for mutating web endpoints.
"""
import secrets
from typing import Optional

from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader

from config import settings

API_KEY_HEADER_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


async def require_api_key(
    api_key: Optional[str] = Security(api_key_header),
) -> str:
    """Require a valid X-API-Key header matching settings.api_key.

    Fails closed: if no API key is configured, all authenticated
    requests are rejected so the control plane cannot be left open.
    """
    expected = (settings.api_key or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key authentication is not configured",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    provided = (api_key or "").strip()
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return provided
