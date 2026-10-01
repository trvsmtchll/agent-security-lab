"""Toy OAuth 2.1 client-credentials issuer for the lab.

Deliberately small and readable: every OAuth concept the threat model
discusses — client authentication, scope narrowing, audience binding,
short-lived RS256 access tokens, JWKS publication — is visible in this
one file. It is NOT a production IdP (see THREAT_MODEL.md).
"""

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
import uuid

import jwt
from cryptography.hazmat.primitives import serialization
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


# --- Invalid-token fixtures for verifier negative tests ----------------------
# These endpoints hand out tokens that a correct verifier MUST reject. They
# exist only so the mcp-server test suite can assert each rejection path
# (TM-10 alg handling, TM-11 audience binding, TM-12 issuer binding). A real
# IdP never issues these; the kill switch below keeps them out of k8s.

_BROKEN_VARIANTS = {
    "none": "alg=none carries no signature (RFC 8725 §2.1)",
    "hs256-confusion": "symmetric alg over an asymmetric key — alg confusion",
    "wrong-aud": "aud is some other service, not this MCP server (TM-11)",
    "wrong-iss": "signed by a key this issuer never publishes (TM-12)",
    "expired": "exp is in the past",
    "hostile-kid": "kid is an injection probe, not a published key id (TM-06)",
}


def _baseline_claims(now: int) -> dict:
    """Otherwise-plausible claims shared by every fixture variant."""
    return {
        "iss": settings.issuer,
        "sub": settings.oauth_client_id,
        "aud": settings.mcp_resource_uri,
        "exp": now + settings.token_ttl_seconds,
        "iat": now,
        "nbf": now,
        "jti": uuid.uuid4().hex,
        "scope": settings.client_scope_ceiling,
    }


def _b64url(raw: bytes) -> str:
    """base64url without padding, as JWS segments are encoded."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _public_pem(keypair: keys.KeyPair) -> bytes:
    """SubjectPublicKeyInfo PEM for the given signing key."""
    private = serialization.load_pem_private_key(
        keypair.private_pem.encode("ascii"), password=None
    )
    return private.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _mint_fixture(variant: str) -> str:
    """Return a token matching the named invalid variant."""
    now = int(time.time())
    claims = _baseline_claims(now)
    current = keys.current_keypair()
    if variant == "none":
        return jwt.encode(claims, key="", algorithm="none")
    if variant == "hs256-confusion":
        # PyJWT refuses to HMAC with an asymmetric key, so assemble the JWS
        # segments by hand: header claims HS256 under the real kid, signature
        # is HMAC-SHA256 over the public key bytes. A verifier that confused
        # the published RSA public key for an HMAC secret would accept it; an
        # RS256-only allowlist (Task 2.4) rejects it outright.
        header = {"alg": "HS256", "kid": current.kid}
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        sig = hmac.new(_public_pem(current), signing_input.encode(), hashlib.sha256)
        return signing_input + "." + _b64url(sig.digest())
    if variant == "wrong-aud":
        claims["aud"] = "http://some-other-service/api"
        return jwt.encode(claims, current.private_pem, algorithm="RS256",
                          headers={"kid": current.kid, "typ": "at+jwt"})
    if variant == "wrong-iss":
        claims["iss"] = "http://evil-issuer:8085"
        foreign = keys.foreign_keypair
        return jwt.encode(claims, foreign.private_pem, algorithm="RS256",
                          headers={"kid": foreign.kid, "typ": "at+jwt"})
    if variant == "expired":
        claims.update(exp=now - 3600, iat=now - 3900, nbf=now - 3900)
        return jwt.encode(claims, current.private_pem, algorithm="RS256",
                          headers={"kid": current.kid, "typ": "at+jwt"})
    if variant == "hostile-kid":
        bad_kid = "../../etc/passwd" + "A" * 10240
        return jwt.encode(claims, current.private_pem, algorithm="RS256",
                          headers={"kid": bad_kid, "typ": "at+jwt"})
    raise KeyError(variant)


@app.get("/demo/mint-broken")
def mint_broken(variant: str = "") -> JSONResponse:
    """Hand out an invalid token for verifier negative tests (TM-03 gated)."""
    if not settings.demo_fixtures_enabled:
        return JSONResponse({"error": "not_found"}, status_code=404)
    if variant not in _BROKEN_VARIANTS:
        return JSONResponse(
            {"error": "invalid_variant", "valid": sorted(_BROKEN_VARIANTS)},
            status_code=400,
        )
    return JSONResponse(
        {
            "access_token": _mint_fixture(variant),
            "variant": variant,
            "why_broken": _BROKEN_VARIANTS[variant],
        }
    )


@app.get("/health")
def health() -> dict:
    """Liveness probe; also exposes the current kid for the demo panel."""
    return {
        "status": "ok",
        "kid": keys.current_keypair().kid,
        "fixtures_enabled": settings.demo_fixtures_enabled,
    }
