"""Tests for the MCP server's HTTP-layer auth gate and metadata (Task 2.7)."""

import inspect
import json

from starlette.testclient import TestClient

import src.server as server
from src import verifier
from src.config import settings
from tests._helpers import KeyFixture


async def _stub_app(scope, receive, send):
    """Trivial inner app: drains the body, returns 200 — detects pass-through."""
    if scope["type"] == "http":
        more = True
        while more:
            event = await receive()
            more = event.get("more_body", False)
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b'{"ok":true}'})


def _call(client: TestClient, tool: str, token: str | None = None):
    body = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
         "params": {"name": tool, "arguments": {}}}
    )
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/mcp", content=body, headers=headers)


class _ServerTestBase:
    def setup_method(self) -> None:
        self.key = KeyFixture("srvkid")
        verifier._cache._known_good = {self.key.kid: self.key.jwk}
        verifier._cache._consecutive_failures = 0
        verifier._cache._opened_at = None
        settings.auth_mode = "enforce"
        settings.auth_failure_mode = "fail_closed"
        self.client = TestClient(server.AuthMiddleware(_stub_app))


class TestMetadataAndHealth:
    """RFC 9728 metadata and health are served and need no auth.

    These routes do not depend on the MCP session-manager lifespan, so the
    TestClient is used without its context manager — entering the lifespan of
    the shared module-level app twice would re-run the single-use streamable
    session manager.
    """

    def test_protected_resource_metadata(self) -> None:
        meta = TestClient(server.app).get(
            "/.well-known/oauth-protected-resource"
        ).json()
        assert meta["resource"] == settings.canonical_uri
        assert meta["authorization_servers"] == [settings.oauth_issuer]
        assert set(meta["scopes_supported"]) == {
            "tools:read", "tools:execute", "tools:write"
        }

    def test_health(self) -> None:
        health = TestClient(server.app).get("/health").json()
        assert health["status"] == "ok"
        assert health["auth_mode"] in {"enforce", "off"}
        assert health["breaker"] in {"closed", "open", "half_open"}


class TestAuthGate(_ServerTestBase):
    def test_no_token_401_with_challenge(self) -> None:  # TM-15
        resp = _call(self.client, "query_database")
        assert resp.status_code == 401
        assert "resource_metadata" in resp.headers.get("www-authenticate", "")

    def test_invalid_token_401(self) -> None:
        resp = _call(self.client, "query_database", "not-a-jwt")
        assert resp.status_code == 401

    def test_valid_token_passes_through(self) -> None:
        resp = _call(self.client, "query_database", self.key.mint(scope="tools:read"))
        assert resp.status_code == 200

    def test_insufficient_scope_403(self) -> None:  # TM-14
        resp = _call(self.client, "execute_command", self.key.mint(scope="tools:read"))
        assert resp.status_code == 403
        assert resp.json()["scope"] == "tools:execute"
        assert "insufficient_scope" in resp.headers.get("www-authenticate", "")

    def test_unknown_tool_default_denied(self) -> None:  # TM-14
        token = self.key.mint(scope="tools:read tools:execute tools:write")
        resp = _call(self.client, "rm_rf", token)
        assert resp.status_code == 403
        assert resp.json()["error"] == "unknown_tool"


class TestAuthModeOff(_ServerTestBase):
    def test_auth_mode_off_bypasses(self) -> None:  # Act 1
        settings.auth_mode = "off"
        try:
            resp = _call(self.client, "execute_command")  # no token
            assert resp.status_code == 200
        finally:
            settings.auth_mode = "enforce"


class TestFailPolicyHTTP(_ServerTestBase):
    class _Down:
        def get_signing_key(self, kid):
            import jwt
            raise jwt.PyJWKClientConnectionError("down")

        def get_signing_keys(self, refresh=False):
            import jwt
            raise jwt.PyJWKClientConnectionError("down")

    def _cold_token(self) -> str:
        verifier._cache._client = self._Down()
        verifier._cache._known_good = {}
        return self.key.mint(headers={"kid": "coldkid"}, scope="tools:read")

    def test_fail_closed_503_retry_after(self) -> None:  # TM-08
        token = self._cold_token()
        settings.auth_failure_mode = "fail_closed"
        resp = _call(self.client, "query_database", token)
        assert resp.status_code == 503
        assert resp.headers.get("retry-after") == "30"

    def test_fail_open_200_degraded_header(self) -> None:  # TM-08
        token = self._cold_token()
        settings.auth_failure_mode = "fail_open"
        resp = _call(self.client, "query_database", token)
        assert resp.status_code == 200
        assert resp.headers.get("x-auth-degraded") == "true"


class TestTokenPassthroughProhibition:
    """TM-13: upstream calls use the server's own creds, never the inbound token."""

    def test_tool_signatures_take_no_token(self) -> None:
        from src import tools

        for name in ("query_database", "fetch_webpage", "execute_command",
                     "github_create_issue"):
            params = set(inspect.signature(getattr(tools, name)).parameters)
            assert "token" not in params
            assert "authorization" not in params

    def test_github_tool_uses_own_credential(self) -> None:
        from src import tools

        # With no server-side PAT configured the tool refuses — it never falls
        # back to an inbound bearer token.
        result = tools.github_create_issue("title", "body")
        assert "GITHUB_PAT not configured" in result
