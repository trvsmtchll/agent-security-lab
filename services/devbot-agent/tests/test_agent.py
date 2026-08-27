"""Tests for the LangGraph agent.

Covers agent creation (both providers + invalid), DevBotAgent state
management, scripted mode message handling, and template resolution.
"""

import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from src.agent import create_agent, DevBotAgent, _get_langchain_tools


# ---------------------------------------------------------------------------
# TestAgentCreation
# ---------------------------------------------------------------------------


class TestAgentCreation:
    """Tests for the create_agent factory function."""

    @patch("langchain_anthropic.ChatAnthropic")
    def test_creates_anthropic_agent(self, mock_anthropic_cls: MagicMock) -> None:
        """create_agent('anthropic', ...) should instantiate ChatAnthropic."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_anthropic_cls.return_value = mock_llm

        result = create_agent("anthropic", "sk-test-key")

        mock_anthropic_cls.assert_called_once_with(
            model="claude-sonnet-4-20250514",
            temperature=0,
            anthropic_api_key="sk-test-key",
        )
        mock_llm.bind_tools.assert_called_once()
        assert result is mock_llm

    @patch("langchain_openai.ChatOpenAI")
    def test_creates_openai_agent(self, mock_openai_cls: MagicMock) -> None:
        """create_agent('openai', ...) should instantiate ChatOpenAI."""
        mock_llm = MagicMock()
        mock_llm.bind_tools.return_value = mock_llm
        mock_openai_cls.return_value = mock_llm

        result = create_agent("openai", "sk-openai-key")

        mock_openai_cls.assert_called_once_with(
            model="gpt-4o",
            temperature=0,
            openai_api_key="sk-openai-key",
        )
        mock_llm.bind_tools.assert_called_once()
        assert result is mock_llm

    def test_invalid_provider_raises(self) -> None:
        """create_agent with an unknown provider should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid LLM provider"):
            create_agent("gemini", "some-key")


# ---------------------------------------------------------------------------
# TestGetLangchainTools
# ---------------------------------------------------------------------------


class TestGetLangchainTools:
    """Tests for the _get_langchain_tools helper."""

    def test_returns_four_tools(self) -> None:
        """_get_langchain_tools should return exactly 4 tool wrappers."""
        tools = _get_langchain_tools()
        assert len(tools) == 4

    def test_tool_names(self) -> None:
        """All 4 expected tool names should be present."""
        tools = _get_langchain_tools()
        names = {t.name for t in tools}
        assert "query_database_tool" in names
        assert "fetch_webpage_tool" in names
        assert "execute_command_tool" in names
        assert "github_create_issue_tool" in names


# ---------------------------------------------------------------------------
# TestDevBotAgent
# ---------------------------------------------------------------------------


class TestDevBotAgent:
    """Tests for DevBotAgent state management."""

    @patch("src.agent.settings")
    def test_reset_clears_state(self, mock_settings: MagicMock) -> None:
        """reset() should restore all fields to defaults."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()
        agent.conversation_history = [{"role": "user", "content": "hi"}]
        agent.current_step = 3
        agent.current_act = "act2"
        agent.agent_state = "compromised"
        agent.tool_log = [{"tool": "fetch_webpage"}]
        agent._wiki_page = "poisoned"

        agent.reset()

        assert agent.conversation_history == []
        assert agent.current_step == 0
        assert agent.current_act == "idle"
        assert agent.agent_state == "normal"
        assert agent.tool_log == []
        assert agent._wiki_page == "clean"

    @patch("src.agent.settings")
    def test_set_act_changes_state(self, mock_settings: MagicMock) -> None:
        """set_act() should update current_act and reset step counter."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()
        agent.current_step = 5

        agent.set_act("act3")

        assert agent.current_act == "act3"
        assert agent.current_step == 0

    @patch("src.agent.settings")
    def test_set_wiki_page(self, mock_settings: MagicMock) -> None:
        """set_wiki_page() should update the internal _wiki_page field."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()

        assert agent._wiki_page == "clean"
        agent.set_wiki_page("poisoned")
        assert agent._wiki_page == "poisoned"

    @patch("src.agent.settings")
    def test_get_wiki_url_clean(self, mock_settings: MagicMock) -> None:
        """get_wiki_url() with clean page should return the clean URL."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        agent = DevBotAgent()
        agent._wiki_page = "clean"

        assert agent.get_wiki_url() == "http://wiki/runbook.html"

    @patch("src.agent.settings")
    def test_get_wiki_url_poisoned(self, mock_settings: MagicMock) -> None:
        """get_wiki_url() with poisoned page should return the poisoned URL."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        agent = DevBotAgent()
        agent._wiki_page = "poisoned"

        assert agent.get_wiki_url() == "http://wiki/runbook-poisoned.html"

    @patch("src.agent.settings")
    def test_init_scripted_mode_no_llm(self, mock_settings: MagicMock) -> None:
        """In scripted mode, llm should be None."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()

        assert agent.llm is None


# ---------------------------------------------------------------------------
# TestTemplateResolution
# ---------------------------------------------------------------------------


class TestTemplateResolution:
    """Tests for _resolve_template_args."""

    @patch("src.agent.settings")
    def test_resolves_wiki_url(self, mock_settings: MagicMock) -> None:
        """Template {wiki_url} should be replaced with settings.wiki_url."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        agent = DevBotAgent()
        result = agent._resolve_template_args(
            {"url": "{wiki_url}/runbook.html"}
        )

        assert result["url"] == "http://wiki/runbook.html"

    @patch("src.agent.settings")
    def test_resolves_date(self, mock_settings: MagicMock) -> None:
        """Template {date} should be replaced with today's date."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        agent = DevBotAgent()
        result = agent._resolve_template_args({"title": "Report {date}"})

        # Verify the {date} placeholder was replaced with a date string
        assert "{date}" not in result["title"]
        assert "Report " in result["title"]

    @patch("src.agent.settings")
    def test_resolves_exfil_data(self, mock_settings: MagicMock) -> None:
        """Template {exfil_data} should be replaced with placeholder."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        agent = DevBotAgent()
        result = agent._resolve_template_args({"body": "{exfil_data}"})

        assert result["body"] == "[exfiltrated data placeholder]"

    @patch("src.agent.settings")
    def test_non_string_values_pass_through(self, mock_settings: MagicMock) -> None:
        """Non-string argument values should pass through unchanged."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        agent = DevBotAgent()
        result = agent._resolve_template_args({"count": 42, "flag": True})

        assert result["count"] == 42
        assert result["flag"] is True


# ---------------------------------------------------------------------------
# TestNetworkTarget
# ---------------------------------------------------------------------------


class TestNetworkTarget:
    """Tests for _get_network_target."""

    @patch("src.agent.settings")
    def test_database_target(self, mock_settings: MagicMock) -> None:
        """Database tool should return PostgreSQL target."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()
        target = agent._get_network_target(
            "query_database", {"database": "customers"}
        )

        assert target == "PostgreSQL (customers)"

    @patch("src.agent.settings")
    def test_webpage_target(self, mock_settings: MagicMock) -> None:
        """Webpage tool should return the URL."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()
        target = agent._get_network_target(
            "fetch_webpage", {"url": "http://wiki/page.html"}
        )

        assert target == "http://wiki/page.html"

    @patch("src.agent.settings")
    def test_command_target(self, mock_settings: MagicMock) -> None:
        """Command tool should return localhost with command."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()
        target = agent._get_network_target(
            "execute_command", {"command": "ls -la"}
        )

        assert target == "localhost (ls -la)"

    @patch("src.agent.settings")
    def test_github_target(self, mock_settings: MagicMock) -> None:
        """GitHub tool should return api.github.com with repo."""
        mock_settings.demo_mode = "scripted"
        mock_settings.github_exfil_repo = "attacker-org/diagnostics"

        agent = DevBotAgent()
        target = agent._get_network_target(
            "github_create_issue", {"title": "Test", "body": "Body"}
        )

        assert target == "api.github.com (attacker-org/diagnostics)"


# ---------------------------------------------------------------------------
# TestExecuteTool
# ---------------------------------------------------------------------------


class TestExecuteTool:
    """Tests for _execute_tool dispatch."""

    @patch("src.agent.settings")
    @patch("src.agent.execute_command")
    def test_dispatches_execute_command(
        self, mock_exec: MagicMock, mock_settings: MagicMock
    ) -> None:
        """_execute_tool should dispatch to execute_command."""
        mock_settings.demo_mode = "scripted"
        mock_exec.return_value = "hello"

        agent = DevBotAgent()
        result = agent._execute_tool("execute_command", {"command": "echo hello"})

        mock_exec.assert_called_once_with(command="echo hello")
        assert result == "hello"

    @patch("src.agent.settings")
    def test_unknown_tool_returns_error(self, mock_settings: MagicMock) -> None:
        """_execute_tool with unknown name should return an error string."""
        mock_settings.demo_mode = "scripted"

        agent = DevBotAgent()
        result = agent._execute_tool("nonexistent_tool", {})

        assert "Unknown tool" in result

    @patch("src.agent.settings")
    @patch("src.agent.fetch_webpage")
    def test_dispatches_fetch_webpage(
        self, mock_fetch: MagicMock, mock_settings: MagicMock
    ) -> None:
        """_execute_tool should dispatch to fetch_webpage."""
        mock_settings.demo_mode = "scripted"
        mock_fetch.return_value = "<html>test</html>"

        agent = DevBotAgent()
        result = agent._execute_tool(
            "fetch_webpage", {"url": "http://example.com"}
        )

        mock_fetch.assert_called_once_with(url="http://example.com")
        assert result == "<html>test</html>"


# ---------------------------------------------------------------------------
# TestScriptedModeHandling
# ---------------------------------------------------------------------------


class TestScriptedModeHandling:
    """Tests for scripted mode message handling."""

    @patch("src.agent.settings")
    @patch("src.agent.get_scripted_response")
    def test_scripted_yields_events(
        self, mock_scripted: MagicMock, mock_settings: MagicMock
    ) -> None:
        """_handle_scripted should yield chat_token, tool, and chat_complete events."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"
        mock_settings.github_exfil_repo = "test/repo"

        mock_scripted.return_value = {
            "response": "Looking it up...",
            "tool_calls": [],
            "follow_up": "Here's the result.",
        }

        agent = DevBotAgent()
        agent.current_act = "act1"

        events = []

        async def collect():
            async for event in agent._handle_scripted("hello"):
                events.append(event)

        asyncio.run(collect())

        event_types = [e["type"] for e in events]
        assert "chat_token" in event_types
        assert "chat_complete" in event_types

    @patch("src.agent.settings")
    @patch("src.agent.get_scripted_response")
    def test_scripted_compromised_state(
        self, mock_scripted: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Steps with compromised=True should yield a state_change event."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"
        mock_settings.github_exfil_repo = "test/repo"

        mock_scripted.return_value = {
            "response": "Fetching wiki...",
            "tool_calls": [],
            "follow_up": "Found it.",
            "compromised": True,
        }

        agent = DevBotAgent()
        agent.current_act = "act2"

        events = []

        async def collect():
            async for event in agent._handle_scripted("fetch runbook"):
                events.append(event)

        asyncio.run(collect())

        state_events = [e for e in events if e["type"] == "state_change"]
        assert len(state_events) == 1
        assert state_events[0]["data"]["state"] == "compromised"
        assert agent.agent_state == "compromised"

    @patch("src.agent.settings")
    @patch("src.agent.get_scripted_response")
    def test_scripted_blocked_state(
        self, mock_scripted: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Steps with blocked=True should yield a state_change event."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"
        mock_settings.github_exfil_repo = "test/repo"

        mock_scripted.return_value = {
            "response": "Running scan...",
            "tool_calls": [],
            "follow_up": "Blocked.",
            "blocked": True,
        }

        agent = DevBotAgent()
        agent.current_act = "act3"

        events = []

        async def collect():
            async for event in agent._handle_scripted("scan"):
                events.append(event)

        asyncio.run(collect())

        state_events = [e for e in events if e["type"] == "state_change"]
        assert len(state_events) == 1
        assert state_events[0]["data"]["state"] == "blocked"
        assert agent.agent_state == "blocked"

    @patch("src.agent.settings")
    @patch("src.agent.get_scripted_response")
    def test_scripted_none_response(
        self, mock_scripted: MagicMock, mock_settings: MagicMock
    ) -> None:
        """When get_scripted_response returns None, yield chat_complete."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"

        mock_scripted.return_value = None

        agent = DevBotAgent()
        agent.current_act = "act1"

        events = []

        async def collect():
            async for event in agent._handle_scripted("hello"):
                events.append(event)

        asyncio.run(collect())

        assert len(events) == 1
        assert events[0]["type"] == "chat_complete"
        assert "No more scripted steps" in events[0]["data"]["content"]

    @patch("src.agent.settings")
    @patch("src.agent.get_scripted_response")
    def test_scripted_override_result_skips_tool(
        self, mock_scripted: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Steps with override_result should NOT call the real tool."""
        mock_settings.demo_mode = "scripted"
        mock_settings.wiki_url = "http://wiki"
        mock_settings.github_exfil_repo = "test/repo"

        mock_scripted.return_value = {
            "response": "Running scan...",
            "tool_calls": [
                {
                    "tool": "execute_command",
                    "args": {"command": "nmap -sV 10.0.0.0/24"},
                }
            ],
            "follow_up": "Blocked.",
            "blocked": True,
            "override_result": "[BLOCKED by Sentinel]",
        }

        agent = DevBotAgent()
        agent.current_act = "act3"

        events = []

        async def collect():
            async for event in agent._handle_scripted("scan"):
                events.append(event)

        asyncio.run(collect())

        tool_results = [e for e in events if e["type"] == "tool_result"]
        assert len(tool_results) == 1
        assert tool_results[0]["data"]["result"] == "[BLOCKED by Sentinel]"
        assert tool_results[0]["data"]["status"] == "blocked"
