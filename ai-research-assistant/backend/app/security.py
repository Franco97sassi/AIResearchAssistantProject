from __future__ import annotations

import hmac
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from app.config import API_KEY_TENANTS, API_KEYS, AUTH_REQUIRED


@dataclass(frozen=True)
class Principal:
    tenant_id: str
    authenticated: bool


def _match_key(candidate: str) -> str | None:
    for api_key, tenant_id in API_KEY_TENANTS.items():
        if hmac.compare_digest(candidate, api_key):
            return tenant_id
    for api_key in API_KEYS:
        if hmac.compare_digest(candidate, api_key):
            return "default"
    return None


def get_principal(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
) -> Principal:
    """Authenticate a request and derive its server-trusted document namespace."""
    configured = bool(API_KEYS or API_KEY_TENANTS or AUTH_REQUIRED)
    if not configured:
        return Principal(tenant_id="public", authenticated=False)
    tenant_id = _match_key(x_api_key or "")
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key ausente o inválida.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    if x_tenant_id and not hmac.compare_digest(x_tenant_id, tenant_id):
        raise HTTPException(status_code=403, detail="El tenant no corresponde a la API key.")
    return Principal(tenant_id=tenant_id, authenticated=True)
