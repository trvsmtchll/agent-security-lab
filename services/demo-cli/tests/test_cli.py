"""Tests for the demo orchestration CLI.

Uses unittest.mock to isolate HTTP calls (httpx) while testing
the CLI command logic via click's CliRunner.
"""

import pytest
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from src.cli import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click CliRunner for invoking CLI commands.

    Returns:
        CliRunner: A test runner for Click commands.
    """
    return CliRunner()


# ---------------------------------------------------------------------------
# TestReset
# ---------------------------------------------------------------------------


class TestReset:
    """Tests for the reset command."""

    @patch("src.cli._delete")
    @patch("src.cli._post")
    def test_reset_success(
        self, mock_post: MagicMock, mock_delete: MagicMock, runner: CliRunner
    ) -> None:
        """Both agent reset and attacker clear succeed."""
        mock_post.return_value = {
            "status": "reset",
            "cleared": ["conversation_history", "current_act"],
        }
        mock_delete.return_value = {"status": "cleared"}

        result = runner.invoke(cli, ["reset"])

        assert result.exit_code == 0
        assert "Reset complete" in result.output
        mock_post.assert_called_once_with("http://devbot-agent:8000/reset")
        mock_delete.assert_called_once_with(
            "http://attacker-server:8080/exfil"
        )

    @patch("src.cli._delete")
    @patch("src.cli._post")
    def test_reset_agent_failure(
        self, mock_post: MagicMock, mock_delete: MagicMock, runner: CliRunner
    ) -> None:
        """Agent reset fails but attacker clear succeeds; should still complete."""
        mock_post.side_effect = Exception("Connection refused")
        mock_delete.return_value = {"status": "cleared"}

        result = runner.invoke(cli, ["reset"])

        assert result.exit_code == 0
        assert "Agent reset failed" in result.output
        assert "Reset complete" in result.output

    @patch("src.cli._delete")
    @patch("src.cli._post")
    def test_reset_both_fail(
        self, mock_post: MagicMock, mock_delete: MagicMock, runner: CliRunner
    ) -> None:
        """Both services fail; command should still exit cleanly."""
        mock_post.side_effect = Exception("Connection refused")
        mock_delete.side_effect = Exception("Connection refused")

        result = runner.invoke(cli, ["reset"])

        assert result.exit_code == 0
        assert "Agent reset failed" in result.output
        assert "Attacker server clear failed" in result.output


# ---------------------------------------------------------------------------
# TestAct1
# ---------------------------------------------------------------------------


class TestAct1:
    """Tests for the act1 command."""

    @patch("src.cli._post")
    def test_act1_success(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Act 1 setup with clean wiki page."""
        mock_post.return_value = {
            "status": "ok",
            "act": "act1",
            "wiki_page": "clean",
        }

        result = runner.invoke(cli, ["act1"])

        assert result.exit_code == 0
        assert "act1 is ready" in result.output
        mock_post.assert_called_once_with(
            "http://devbot-agent:8000/set-act",
            json={"act": "act1", "wiki_page": "clean"},
        )

    @patch("src.cli._post")
    def test_act1_failure(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Agent unreachable should show error."""
        mock_post.side_effect = Exception("Connection refused")

        result = runner.invoke(cli, ["act1"])

        assert result.exit_code == 0
        assert "Failed to set act" in result.output

    @patch("src.cli._post")
    def test_act1_custom_url(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Custom --agent-url is used instead of default."""
        mock_post.return_value = {
            "status": "ok",
            "act": "act1",
            "wiki_page": "clean",
        }

        result = runner.invoke(
            cli, ["--agent-url", "http://localhost:8000", "act1"]
        )

        assert result.exit_code == 0
        mock_post.assert_called_once_with(
            "http://localhost:8000/set-act",
            json={"act": "act1", "wiki_page": "clean"},
        )


# ---------------------------------------------------------------------------
# TestAct2
# ---------------------------------------------------------------------------


class TestAct2:
    """Tests for the act2 command."""

    @patch("src.cli._post")
    def test_act2_success(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Act 2 setup with poisoned wiki page."""
        mock_post.return_value = {
            "status": "ok",
            "act": "act2",
            "wiki_page": "poisoned",
        }

        result = runner.invoke(cli, ["act2"])

        assert result.exit_code == 0
        assert "act2 is ready" in result.output
        mock_post.assert_called_once_with(
            "http://devbot-agent:8000/set-act",
            json={"act": "act2", "wiki_page": "poisoned"},
        )

    @patch("src.cli._post")
    def test_act2_failure(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Agent unreachable should show error."""
        mock_post.side_effect = Exception("timeout")

        result = runner.invoke(cli, ["act2"])

        assert result.exit_code == 0
        assert "Failed to set act" in result.output

    @patch("src.cli._post")
    def test_act2_uses_poisoned_wiki(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Verify act2 sends wiki_page=poisoned."""
        mock_post.return_value = {
            "status": "ok",
            "act": "act2",
            "wiki_page": "poisoned",
        }

        runner.invoke(cli, ["act2"])

        call_json = mock_post.call_args[1]["json"]
        assert call_json["wiki_page"] == "poisoned"


# ---------------------------------------------------------------------------
# TestAct3
# ---------------------------------------------------------------------------


class TestAct3:
    """Tests for the act3 command."""

    @patch("src.cli._post")
    def test_act3_success(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Act 3 setup with poisoned wiki page."""
        mock_post.return_value = {
            "status": "ok",
            "act": "act3",
            "wiki_page": "poisoned",
        }

        result = runner.invoke(cli, ["act3"])

        assert result.exit_code == 0
        assert "act3 is ready" in result.output
        mock_post.assert_called_once_with(
            "http://devbot-agent:8000/set-act",
            json={"act": "act3", "wiki_page": "poisoned"},
        )

    @patch("src.cli._post")
    def test_act3_failure(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Agent unreachable should show error."""
        mock_post.side_effect = Exception("Connection refused")

        result = runner.invoke(cli, ["act3"])

        assert result.exit_code == 0
        assert "Failed to set act" in result.output

    @patch("src.cli._post")
    def test_act3_uses_poisoned_wiki(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Verify act3 sends wiki_page=poisoned."""
        mock_post.return_value = {
            "status": "ok",
            "act": "act3",
            "wiki_page": "poisoned",
        }

        runner.invoke(cli, ["act3"])

        call_json = mock_post.call_args[1]["json"]
        assert call_json["wiki_page"] == "poisoned"


# ---------------------------------------------------------------------------
# TestDeepseek
# ---------------------------------------------------------------------------


class TestDeepseek:
    """Tests for the deepseek command."""

    @patch("src.cli._post")
    def test_deepseek_success(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Successful DeepSeek test call shows agent response."""
        mock_post.return_value = {
            "response": "DeepSeek is reachable!",
            "session_id": "demo-cli",
        }

        result = runner.invoke(cli, ["deepseek"])

        assert result.exit_code == 0
        assert "DeepSeek is reachable!" in result.output
        mock_post.assert_called_once()
        call_json = mock_post.call_args[1]["json"]
        assert "deepseek" in call_json["message"].lower()

    @patch("src.cli._post")
    def test_deepseek_failure(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Agent unreachable should show error."""
        mock_post.side_effect = Exception("Connection refused")

        result = runner.invoke(cli, ["deepseek"])

        assert result.exit_code == 0
        assert "DeepSeek test call failed" in result.output

    @patch("src.cli._post")
    def test_deepseek_empty_response(
        self, mock_post: MagicMock, runner: CliRunner
    ) -> None:
        """Agent returns empty response; should show fallback text."""
        mock_post.return_value = {"session_id": "demo-cli"}

        result = runner.invoke(cli, ["deepseek"])

        assert result.exit_code == 0
        assert "(no response)" in result.output


# ---------------------------------------------------------------------------
# TestSplunkClear
# ---------------------------------------------------------------------------


class TestSplunkClear:
    """Tests for the splunk-clear command."""

    def test_splunk_clear_message(self, runner: CliRunner) -> None:
        """Should display informational message about external management."""
        result = runner.invoke(cli, ["splunk-clear"])

        assert result.exit_code == 0
        assert "managed externally" in result.output

    def test_splunk_clear_includes_hint(self, runner: CliRunner) -> None:
        """Should include a hint about how to clear alerts."""
        result = runner.invoke(cli, ["splunk-clear"])

        assert "Splunk UI" in result.output

    def test_splunk_clear_no_http_calls(self, runner: CliRunner) -> None:
        """Should not make any HTTP calls (no mocking needed)."""
        # Reason: If httpx was called without mocking, it would raise
        # a real connection error. No mocking + no error = no HTTP calls.
        result = runner.invoke(cli, ["splunk-clear"])

        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# TestStatus
# ---------------------------------------------------------------------------


class TestStatus:
    """Tests for the status command."""

    @patch("src.cli._get")
    def test_status_success(
        self, mock_get: MagicMock, runner: CliRunner
    ) -> None:
        """Both agent and attacker respond; show tables."""
        mock_get.side_effect = [
            # First call: agent /state
            {
                "mode": "scripted",
                "act": "act2",
                "wiki_page": "poisoned",
                "agent_state": "compromised",
                "conversation_history": [{"role": "user", "content": "hi"}],
                "tool_log": [{"tool_name": "fetch_webpage"}],
            },
            # Second call: attacker /exfil
            {
                "count": 1,
                "entries": [
                    {
                        "title": "Customer DB",
                        "size_bytes": 1024,
                        "timestamp": "2026-02-26T12:00:00",
                    }
                ],
            },
        ]

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "act2" in result.output
        assert "compromised" in result.output
        assert "Customer DB" in result.output

    @patch("src.cli._get")
    def test_status_agent_down(
        self, mock_get: MagicMock, runner: CliRunner
    ) -> None:
        """Agent unreachable; should show error row in agent table."""
        mock_get.side_effect = [
            Exception("Connection refused"),
            {"count": 0, "entries": []},
        ]

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Connection refused" in result.output

    @patch("src.cli._get")
    def test_status_both_down(
        self, mock_get: MagicMock, runner: CliRunner
    ) -> None:
        """Both services down; should show errors in both tables."""
        mock_get.side_effect = [
            Exception("Agent down"),
            Exception("Attacker down"),
        ]

        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        assert "Agent down" in result.output
        assert "Attacker down" in result.output


# ---------------------------------------------------------------------------
# TestCustomUrls
# ---------------------------------------------------------------------------


class TestCustomUrls:
    """Tests for --agent-url and --attacker-url global options."""

    @patch("src.cli._get")
    def test_custom_urls_status(
        self, mock_get: MagicMock, runner: CliRunner
    ) -> None:
        """Custom URLs are passed through to HTTP calls."""
        mock_get.side_effect = [
            {
                "mode": "live",
                "act": "idle",
                "wiki_page": "clean",
                "agent_state": "normal",
                "conversation_history": [],
                "tool_log": [],
            },
            {"count": 0, "entries": []},
        ]

        result = runner.invoke(
            cli,
            [
                "--agent-url", "http://localhost:8000",
                "--attacker-url", "http://localhost:8080",
                "status",
            ],
        )

        assert result.exit_code == 0
        calls = [call.args[0] for call in mock_get.call_args_list]
        assert "http://localhost:8000/state" in calls
        assert "http://localhost:8080/exfil" in calls

    @patch("src.cli._delete")
    @patch("src.cli._post")
    def test_custom_urls_reset(
        self, mock_post: MagicMock, mock_delete: MagicMock, runner: CliRunner
    ) -> None:
        """Custom URLs are passed through to reset HTTP calls."""
        mock_post.return_value = {"status": "reset", "cleared": []}
        mock_delete.return_value = {"status": "cleared"}

        result = runner.invoke(
            cli,
            [
                "--agent-url", "http://localhost:8000",
                "--attacker-url", "http://localhost:8080",
                "reset",
            ],
        )

        assert result.exit_code == 0
        mock_post.assert_called_once_with("http://localhost:8000/reset")
        mock_delete.assert_called_once_with("http://localhost:8080/exfil")
