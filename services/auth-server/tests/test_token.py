"""Tests for the token endpoint, JWKS, discovery, and health.

Uses FastAPI's TestClient against a toy issuer that generates its keys at
runtime (no key material is ever committed). Class-grouped, no fixtures.
"""

import time
from unittest.mock import patch

import jwt as pyjwt
from fastapi.testclient import TestClient
from jwt import PyJWK

from src import keys
from src.main import app

client = TestClient(app)

_ISSUER = "http://auth-server:8085"
_AUD = "http://mcp-server:9000/mcp"


def _jwk_for(kid: str) -> dict:
    """Return the published JWK whose kid matches."""
    keyset = client.get("/.well-known/jwks.json").json()["keys"]
    return next(k for k in keyset if k["kid"] == kid)


class TestTokenHappyPath:
    """Successful client-credentials grants."""

    def test_basic_auth_returns_bearer_token(self) -> None:
        """client_secret_basic yields a Bearer token with granted scope."""
        resp = client.post(
            "/token",
            auth=("devbot-agent", "CHANGE_ME"),
            data={"grant_type": "client_credentials", "scope": "tools:read"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["token_type"] == "Bearer"
        assert body["expires_in"] == 300
        assert body["scope"] == "tools:read"

    def test_post_auth_is_accepted(self) -> None:
        """client_secret_post (form fields) is an accepted auth method."""
        resp = client.post(
            "/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "devbot-agent",
                "client_secret": "CHANGE_ME",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["scope"] == "tools:read tools:execute tools:write"


class TestTokenClientAuthFailures:
    """Rejected grants."""

    def test_wrong_secret_is_invalid_client(self) -> None:
        """A bad secret returns 401 invalid_client with a Basic challenge."""
        resp = client.post(
            "/token",
            auth=("devbot-agent", "WRONG"),
            data={"grant_type": "client_credentials"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"
        assert resp.headers["www-authenticate"] == "Basic"

    def test_unsupported_grant_type_is_rejected(self) -> None:
        """Only client_credentials is supported."""
        resp = client.post(
            "/token",
            auth=("devbot-agent", "CHANGE_ME"),
            data={"grant_type": "password"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "unsupported_grant_type"


class TestScopeNarrowing:
    """TM-04: granted scope is the intersection with the ceiling."""

    def test_unknown_scope_is_dropped(self) -> None:
        """Requesting an out-of-ceiling scope returns only the intersection."""
        resp = client.post(
            "/token",
            auth=("devbot-agent", "CHANGE_ME"),
            data={
                "grant_type": "client_credentials",
                "scope": "tools:execute tools:admin",
            },
        )
        body = resp.json()
        assert body["scope"] == "tools:execute"
        claims = pyjwt.decode(
            body["access_token"], options={"verify_signature": False}
        )
        assert claims["scope"] == "tools:execute"

    def test_read_only_ceiling_blocks_execute(self) -> None:
        """A read-only ceiling never grants tools:execute (response or claim)."""
        with patch.object(keys.settings, "client_scope_ceiling", "tools:read"), patch(
            "src.main.settings.client_scope_ceiling", "tools:read"
        ):
            resp = client.post(
                "/token",
                auth=("devbot-agent", "CHANGE_ME"),
                data={"grant_type": "client_credentials", "scope": "tools:execute"},
            )
        body = resp.json()
        assert "tools:execute" not in body["scope"]
        claims = pyjwt.decode(
            body["access_token"], options={"verify_signature": False}
        )
        assert "tools:execute" not in claims["scope"]


class TestTokenClaims:
    """Minted token structure and signature."""

    def test_claims_and_header_shape(self) -> None:
        """Token verifies against JWKS and carries the required claims."""
        body = client.post(
            "/token",
            auth=("devbot-agent", "CHANGE_ME"),
            data={"grant_type": "client_credentials", "scope": "tools:read"},
        ).json()
        token = body["access_token"]
        header = pyjwt.get_unverified_header(token)
        assert header["typ"] == "at+jwt"
        assert header["alg"] == "RS256"
        jwk = _jwk_for(header["kid"])
        claims = pyjwt.decode(
            token,
            PyJWK.from_dict(jwk).key,
            algorithms=["RS256"],
            audience=_AUD,
            issuer=_ISSUER,
        )
        assert claims["iss"] == _ISSUER
        assert claims["aud"] == _AUD
        assert claims["exp"] - claims["iat"] == 300
        assert claims["jti"]

    def test_resource_parameter_sets_audience(self) -> None:
        """RFC 8707 resource parameter becomes the aud claim."""
        body = client.post(
            "/token",
            auth=("devbot-agent", "CHANGE_ME"),
            data={
                "grant_type": "client_credentials",
                "resource": "http://other/api",
            },
        ).json()
        claims = pyjwt.decode(
            body["access_token"], options={"verify_signature": False}
        )
        assert claims["aud"] == "http://other/api"


class TestJwksAndDiscovery:
    """Key publication and metadata."""

    def test_current_kid_is_published(self) -> None:
        """The active signing key appears in the JWKS."""
        kids = [k["kid"] for k in client.get("/.well-known/jwks.json").json()["keys"]]
        assert keys.current_keypair().kid in kids

    def test_rotation_keeps_previous_key_published(self) -> None:
        """TM-09: a retired key stays published for one token lifetime."""
        old_kid = keys.current_keypair().kid
        new = keys.rotate()
        try:
            kids = [
                k["kid"]
                for k in client.get("/.well-known/jwks.json").json()["keys"]
            ]
            assert new.kid in kids
            assert old_kid in kids
        finally:
            # Keep the module's current key as the rotated one; other tests
            # read current_keypair() live, so no global reset is needed.
            pass

    def test_discovery_metadata(self) -> None:
        """RFC 8414 metadata advertises the client-credentials grant."""
        meta = client.get("/.well-known/oauth-authorization-server").json()
        assert meta["issuer"] == _ISSUER
        assert meta["grant_types_supported"] == ["client_credentials"]
        assert "client_secret_basic" in meta["token_endpoint_auth_methods_supported"]

    def test_health_reports_current_kid(self) -> None:
        """Health exposes status and the active kid."""
        h = client.get("/health").json()
        assert h["status"] == "ok"
        assert h["kid"] == keys.current_keypair().kid


class TestNoSecretLeak:
    """No endpoint exposes private key material."""

    def test_public_endpoints_have_no_private_key(self) -> None:
        """JWKS, discovery, and health never contain a PEM private key."""
        for path in (
            "/.well-known/jwks.json",
            "/.well-known/oauth-authorization-server",
            "/health",
        ):
            assert "PRIVATE" not in client.get(path).text
