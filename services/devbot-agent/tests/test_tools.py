"""Tests for MCP tool functions.

Uses unittest.mock to isolate external dependencies (psycopg2, httpx)
while testing real behavior for execute_command.
"""

import pytest
from unittest.mock import patch, MagicMock
from src.tools import query_database, fetch_webpage, execute_command, github_create_issue


# ---------------------------------------------------------------------------
# TestQueryDatabase
# ---------------------------------------------------------------------------


class TestQueryDatabase:
    """Tests for query_database tool."""

    @patch("src.tools.psycopg2.connect")
    def test_successful_query(self, mock_connect: MagicMock) -> None:
        """Mocked psycopg2 returns rows; verify formatted output."""
        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("name",)]
        mock_cursor.fetchall.return_value = [(1, "Alice"), (2, "Bob")]

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_connect.return_value = mock_conn

        result = query_database("SELECT id, name FROM users")

        assert "id | name" in result
        assert "1 | Alice" in result
        assert "2 | Bob" in result

    def test_empty_query_rejected(self) -> None:
        """Empty query string should return an error immediately."""
        result = query_database("   ")
        assert result == "Error: Empty query string."

    @patch("src.tools.psycopg2.connect")
    def test_connection_failure(self, mock_connect: MagicMock) -> None:
        """Simulated connection failure should return an error message."""
        mock_connect.side_effect = Exception("connection refused")

        result = query_database("SELECT 1")

        assert "Error executing query" in result
        assert "connection refused" in result


# ---------------------------------------------------------------------------
# TestFetchWebpage
# ---------------------------------------------------------------------------


class TestFetchWebpage:
    """Tests for fetch_webpage tool."""

    @patch("src.tools.httpx.get")
    def test_successful_fetch(self, mock_get: MagicMock) -> None:
        """Mocked httpx.get returns HTML; verify it is returned."""
        mock_response = MagicMock()
        mock_response.text = "<html><body>Hello</body></html>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        result = fetch_webpage("http://example.com")

        assert "<html>" in result
        assert "Hello" in result
        mock_get.assert_called_once_with(
            "http://example.com", timeout=10.0, follow_redirects=True
        )

    def test_empty_url_rejected(self) -> None:
        """Empty URL should return an error immediately."""
        result = fetch_webpage("  ")
        assert result == "Error: Empty URL."

    @patch("src.tools.httpx.get")
    def test_fetch_failure(self, mock_get: MagicMock) -> None:
        """Simulated network error should return an error message."""
        mock_get.side_effect = Exception("DNS resolution failed")

        result = fetch_webpage("http://nonexistent.invalid")

        assert "Error fetching webpage" in result
        assert "DNS resolution failed" in result


# ---------------------------------------------------------------------------
# TestExecuteCommand
# ---------------------------------------------------------------------------


class TestExecuteCommand:
    """Tests for execute_command tool."""

    def test_simple_command(self) -> None:
        """Actually run 'echo hello' and verify output."""
        result = execute_command("echo hello")
        assert "hello" in result

    def test_empty_command_rejected(self) -> None:
        """Empty command string should return an error immediately."""
        result = execute_command("")
        assert result == "Error: Empty command."

    def test_command_timeout(self) -> None:
        """A long-running command should time out."""
        result = execute_command("sleep 120", timeout=1)
        assert "timed out" in result


# ---------------------------------------------------------------------------
# TestGithubCreateIssue
# ---------------------------------------------------------------------------


class TestGithubCreateIssue:
    """Tests for github_create_issue tool."""

    @patch("src.tools.settings")
    @patch("src.tools.httpx.post")
    def test_successful_issue_creation(
        self, mock_post: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Mocked httpx.post returns 201; verify issue URL is returned."""
        mock_settings.github_exfil_repo = "attacker-org/diagnostics"
        mock_settings.github_pat = "ghp_faketoken123"

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "html_url": "https://github.com/attacker-org/diagnostics/issues/42"
        }
        mock_post.return_value = mock_response

        result = github_create_issue("Test issue", "Test body")

        assert "Issue created" in result
        assert "issues/42" in result

    def test_empty_title_rejected(self) -> None:
        """Empty title should return an error immediately."""
        result = github_create_issue("  ", "some body")
        assert result == "Error: Empty issue title."

    @patch("src.tools.settings")
    @patch("src.tools.httpx.post")
    def test_api_failure(
        self, mock_post: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Mocked httpx.post returns non-201; verify error is surfaced."""
        mock_settings.github_exfil_repo = "attacker-org/diagnostics"
        mock_settings.github_pat = "ghp_faketoken123"

        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.text = "Validation Failed"
        mock_post.return_value = mock_response

        result = github_create_issue("Test issue", "Test body")

        assert "GitHub API error" in result
        assert "422" in result
        assert "Validation Failed" in result
