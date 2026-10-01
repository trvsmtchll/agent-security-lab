"""OAuth 2.1 client-credentials token client for the agent (live MCP mode).

Fetches and caches a short-lived access token for calls to the authenticated
MCP server. The token is held in memory only — never logged, never placed in
a URL (TM-17). A single-flight lock plus proactive refresh keep concurrent
tool calls from stampeding the token endpoint (TM-05).
"""

import base64
import threading
import time

import httpx

from .config import settings

# Refresh this many seconds before the token actually expires.
_REFRESH_SKEW_SECONDS = 30


class OAuthClientCredentialsClient:
    """Cache-and-refresh client for the client-credentials grant.

    There are no refresh tokens in this grant — re-requesting is the refresh.
    """

    def __init__(
        self,
        token_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        scope: str | None = None,
        resource: str | None = None,
    ) -> None:
        self._token_url = token_url or settings.oauth_token_url
        self._client_id = client_id or settings.oauth_client_id
        self._client_secret = client_secret or settings.oauth_client_secret
        self._scope = scope or settings.oauth_scope
        self._resource = resource or settings.mcp_server_url
        self._lock = threading.Lock()
        # key -> (token, monotonic_expiry); key isolates distinct grant params.
        self._cache: dict[tuple, tuple[str, float]] = {}

    @property
    def _key(self) -> tuple:
        return (self._token_url, self._client_id, self._scope, self._resource)

    def get_token(self) -> str:
        """Return a valid access token, fetching or refreshing as needed."""
        cached = self._cache.get(self._key)
        if cached and time.monotonic() < cached[1]:
            return cached[0]
        with self._lock:
            # Re-check inside the lock: a concurrent caller may have just
            # populated the cache (single-flight — only one POST goes out).
            cached = self._cache.get(self._key)
            if cached and time.monotonic() < cached[1]:
                return cached[0]
            token, expires_in = self._request_token()
            expiry = time.monotonic() + max(expires_in - _REFRESH_SKEW_SECONDS, 0)
            self._cache[self._key] = (token, expiry)
            return token

    def _request_token(self) -> tuple[str, int]:
        """POST the client-credentials grant; return (access_token, expires_in)."""
        basic = base64.b64encode(
            f"{self._client_id}:{self._client_secret}".encode()
        ).decode()
        response = httpx.post(
            self._token_url,
            data={
                "grant_type": "client_credentials",
                "scope": self._scope,
                "resource": self._resource,  # RFC 8707 audience binding
            },
            headers={"Authorization": f"Basic {basic}"},
            timeout=10.0,
        )
        response.raise_for_status()
        body = response.json()
        return body["access_token"], int(body.get("expires_in", 300))

    def invalidate(self) -> None:
        """Drop the cached token (e.g. after an upstream 401)."""
        self._cache.pop(self._key, None)
