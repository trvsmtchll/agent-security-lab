"""Toy OAuth 2.1 client-credentials issuer for the lab.

Deliberately small and readable: every OAuth concept the threat model
discusses — client authentication, scope narrowing, audience binding,
short-lived RS256 access tokens, JWKS publication — is visible in this
one file. It is NOT a production IdP (see THREAT_MODEL.md).
"""

import base64
import binascii
import secrets
import time
import uuid

import jwt
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from . import keys
from .config import settings

app = FastAPI(title="auth-server", docs_url=None, redoc_url=None)


def _extract_client_auth(request: Request, form: dict) -> tuple[str, str]:
    """Return (client_id, client_secret) from Basic auth or form fields.

    Supports both token_endpoint_auth_methods: client_secret_basic takes
    precedence over client_secret_post when both are present.
    """
    header = request.headers.get("authorization", "")
    if header.lower().startswith("basic "):
        try:
            decoded = base64.b64decode(header[6:], validate=True).decode("utf-8")
            client_id, _, client_secret = decoded.partition(":")
            return client_id, client_secret
        except (binascii.Error, UnicodeDecodeError):
            return "", ""
    return str(form.get("client_id", "")), str(form.get("client_secret", ""))


def _valid_client(client_id: str, client_secret: str) -> bool:
    """Check client credentials in constant time (no early exit on id)."""
    id_ok = secrets.compare_digest(client_id, settings.oauth_client_id)
    secret_ok = secrets.compare_digest(client_secret, settings.oauth_client_secret)
    return id_ok and secret_ok


def _narrow_scope(requested: str | None) -> str:
    """TM-04: granted = requested ∩ ceiling; full ceiling when none requested.

    The granted string preserves ceiling order so output is deterministic.
    """
    ceiling = settings.client_scope_ceiling.split()
    if not requested:
        return " ".join(ceiling)
    wanted = set(requested.split())
    return " ".join(s for s in ceiling if s in wanted)


@app.post("/token")
async def token(request: Request) -> JSONResponse:
    """OAuth 2.1 client-credentials token endpoint (RS256 at+jwt)."""
    form = dict(await request.form())
    client_id, client_secret = _extract_client_auth(request, form)
    # Reason: never log the secret — not even on failure; 401 carries the
    # WWW-Authenticate challenge required for client_secret_basic.
    if not _valid_client(client_id, client_secret):
        return JSONResponse(
            {"error": "invalid_client"},
            status_code=401,
            headers={"WWW-Authenticate": "Basic"},
        )
    if form.get("grant_type") != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    granted = _narrow_scope(form.get("scope"))
    # RFC 8707: the resource parameter becomes the token's audience.
    audience = str(form.get("resource") or settings.mcp_resource_uri)
    now = int(time.time())
    keypair = keys.current_keypair()
    claims = {
        "iss": settings.issuer,
        "sub": client_id,
        "aud": audience,
        "exp": now + settings.token_ttl_seconds,
        "iat": now,
        "nbf": now,
        "jti": uuid.uuid4().hex,
        "scope": granted,
    }
    access_token = jwt.encode(
        claims,
        keypair.private_pem,
        algorithm="RS256",
        headers={"kid": keypair.kid, "typ": "at+jwt"},
    )
    return JSONResponse(
        {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": settings.token_ttl_seconds,
            "scope": granted,
        }
    )


@app.get("/.well-known/jwks.json")
def jwks() -> dict:
    """Published JWKS: current key plus recently retired keys (TM-09)."""
    return keys.published_jwks()


@app.get("/.well-known/oauth-authorization-server")
def discovery() -> dict:
    """RFC 8414 authorization-server metadata."""
    return {
        "issuer": settings.issuer,
        "token_endpoint": f"{settings.issuer}/token",
        "jwks_uri": f"{settings.issuer}/.well-known/jwks.json",
        "grant_types_supported": ["client_credentials"],
        "token_endpoint_auth_methods_supported": [
            "client_secret_basic",
            "client_secret_post",
        ],
        "scopes_supported": settings.client_scope_ceiling.split(),
    }


@app.get("/health")
def health() -> dict:
    """Liveness probe; also exposes the current kid for the demo panel."""
    return {
        "status": "ok",
        "kid": keys.current_keypair().kid,
        "fixtures_enabled": settings.demo_fixtures_enabled,
    }
