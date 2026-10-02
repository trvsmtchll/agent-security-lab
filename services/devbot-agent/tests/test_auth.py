"""Tests for the OAuth client-credentials token client (Task 3.2).

httpx is mocked throughout — no network. Repo style: class-grouped,
unittest.mock, no fixtures/conftest.
"""

import base64
import logging
import threading
import time
from unittest.mock import MagicMock, patch

from src.auth import OAuthClientCredentialsClient


def _token_response(access_token: str = "tok-abc", expires_in: int = 300) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": "tools:read",
    }
    resp.raise_for_status.return_value = None
    return resp


class TestTokenCaching:
    """A valid cached token is reused without a second POST."""

    @patch("src.auth.httpx.post")
    def test_cache_hit_avoids_second_post(self, mock_post) -> None:
        mock_post.return_value = _token_response()
        client = OAuthClientCredentialsClient(
            token_url="http://auth/token", client_id="devbot-agent",
            client_secret="s", scope="tools:read", resource="http://mcp/mcp",
        )
        assert client.get_token() == "tok-abc"
        assert client.get_token() == "tok-abc"
        assert mock_post.call_count == 1

    @patch("src.auth.httpx.post")
    def test_expiry_triggers_refetch(self, mock_post) -> None:
        mock_post.side_effect = [
            _token_response("tok-1"), _token_response("tok-2"),
        ]
        client = OAuthClientCredentialsClient(
            token_url="http://auth/token", client_id="devbot-agent",
            client_secret="s", scope="tools:read", resource="http://mcp/mcp",
        )
        assert client.get_token() == "tok-1"
        # Force the cached entry to look expired.
        client._cache[client._key] = ("tok-1", time.monotonic() - 1)
        assert client.get_token() == "tok-2"
        assert mock_post.call_count == 2


class TestRequestShape:
    """The POST uses client_secret_basic, scope, and the resource parameter."""

    @patch("src.auth.httpx.post")
    def test_basic_auth_and_resource(self, mock_post) -> None:
        mock_post.return_value = _token_response()
        client = OAuthClientCredentialsClient(
            token_url="http://auth/token", client_id="devbot-agent",
            client_secret="sekret", scope="tools:read", resource="http://mcp/mcp",
        )
        client.get_token()
        _, kwargs = mock_post.call_args
        assert kwargs["data"]["grant_type"] == "client_credentials"
        assert kwargs["data"]["scope"] == "tools:read"
        assert kwargs["data"]["resource"] == "http://mcp/mcp"  # RFC 8707
        expected = base64.b64encode(b"devbot-agent:sekret").decode()
        assert kwargs["headers"]["Authorization"] == f"Basic {expected}"


class TestSingleFlight:
    """Concurrent callers trigger exactly one token request (TM-05)."""

    @patch("src.auth.httpx.post")
    def test_concurrent_calls_make_one_post(self, mock_post) -> None:
        def slow_response(*args, **kwargs):
            time.sleep(0.05)  # widen the race window
            return _token_response()

        mock_post.side_effect = slow_response
        client = OAuthClientCredentialsClient(
            token_url="http://auth/token", client_id="devbot-agent",
            client_secret="s", scope="tools:read", resource="http://mcp/mcp",
        )
        results: list[str] = []

        def worker() -> None:
            results.append(client.get_token())

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert results == ["tok-abc"] * 5
        assert mock_post.call_count == 1


class TestNoTokenLeak:
    """The token is never written to logs (TM-17)."""

    @patch("src.auth.httpx.post")
    def test_token_absent_from_logs(self, mock_post) -> None:
        mock_post.return_value = _token_response("super-secret-token")
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        root = logging.getLogger()
        root.addHandler(handler)
        try:
            client = OAuthClientCredentialsClient(
                token_url="http://auth/token", client_id="devbot-agent",
                client_secret="s", scope="tools:read", resource="http://mcp/mcp",
            )
            token = client.get_token()
        finally:
            root.removeHandler(handler)
        assert token == "super-secret-token"
        for record in records:
            assert "super-secret-token" not in record.getMessage()
