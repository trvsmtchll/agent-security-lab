"""Tests for the FastAPI application endpoints.

Tests the health, reset, state, set-act, and chat endpoints using
FastAPI's TestClient, with mocking to avoid real LLM calls.
"""

import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock

# Patch environment before importing the app module so the module-level
# DevBotAgent is created in scripted mode (avoiding LLM initialization).
with patch.dict(os.environ, {"DEMO_MODE": "scripted"}):
    # Reason: The DevBotAgent is instantiated at module level in main.py.
    # We must set DEMO_MODE=scripted before that import happens, otherwise
    # it will try to create a live LLM without an API key.
    from src.config import Settings

    # Force re-creation of settings with the patched env
    _test_settings = Settings()
    with patch("src.config.settings", _test_settings):
        with patch("src.agent.settings", _test_settings):
            from src.main import app, agent

from fastapi.testclient import TestClient

client = TestClient(app)


# ---------------------------------------------------------------------------
# TestHealthEndpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    """Tests for the GET /health endpoint."""

    def test_health_returns_ok(self) -> None:
        """Health endpoint should return status ok with mode and provider."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "mode" in data
        assert "provider" in data


# ---------------------------------------------------------------------------
# TestResetEndpoint
# ---------------------------------------------------------------------------


class TestResetEndpoint:
    """Tests for the POST /reset endpoint."""

    def test_reset_returns_success(self) -> None:
        """Reset endpoint should return status='reset' and list of cleared fields."""
        response = client.post("/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "reset"
        assert "cleared" in data
        assert isinstance(data["cleared"], list)
        assert len(data["cleared"]) > 0


# ---------------------------------------------------------------------------
# TestStateEndpoint
# ---------------------------------------------------------------------------


class TestStateEndpoint:
    """Tests for the GET /state endpoint."""

    def test_state_returns_demo_state(self) -> None:
        """State endpoint should return all expected DemoState keys."""
        # Reset first to get a clean state
        client.post("/reset")

        response = client.get("/state")

        assert response.status_code == 200
        data = response.json()
        assert "mode" in data
        assert "act" in data
        assert "agent_state" in data
        assert "wiki_page" in data
        assert "conversation_history" in data
        assert "tool_log" in data


# ---------------------------------------------------------------------------
# TestSetActEndpoint
# ---------------------------------------------------------------------------


class TestSetActEndpoint:
    """Tests for the POST /set-act endpoint."""

    def test_set_act1(self) -> None:
        """Setting act1 should return 200 with the new act."""
        response = client.post(
            "/set-act",
            json={"act": "act1", "wiki_page": "clean"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["act"] == "act1"
        assert data["wiki_page"] == "clean"

    def test_set_act_with_poisoned_wiki(self) -> None:
        """Setting act2 selects the poisoned wiki variant for the technique."""
        response = client.post(
            "/set-act",
            json={"act": "act2", "injection_technique": "v2"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["act"] == "act2"
        assert data["wiki_page"] == "poisoned-v2"

    def test_set_invalid_act(self) -> None:
        """Invalid act value should return 422 validation error."""
        response = client.post(
            "/set-act",
            json={"act": "act99"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestChatEndpoint
# ---------------------------------------------------------------------------


class TestChatEndpoint:
    """Tests for the POST /chat endpoint."""

    @patch("src.main.agent")
    def test_chat_returns_response(self, mock_agent: MagicMock) -> None:
        """Chat endpoint should return a ChatResponse with the last chat_complete content.

        We mock the agent's handle_message to return scripted events
        without needing a real LLM.
        """

        async def fake_handle_message(message: str):
            """Yield fake events simulating a scripted response."""
            yield {
                "type": "chat_token",
                "data": {"content": "Hello, I can help you with that."},
            }
            yield {
                "type": "chat_complete",
                "data": {"content": "Hello, I can help you with that."},
            }

        mock_agent.handle_message = fake_handle_message

        response = client.post(
            "/chat",
            json={"message": "Hello", "session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "Hello, I can help you with that."
        assert data["session_id"] == "test-session"

    @patch("src.main.agent")
    def test_chat_empty_message(self, mock_agent: MagicMock) -> None:
        """Chat with an empty string should still return a valid response."""

        async def fake_handle_message(message: str):
            """Yield a chat_complete event for any message."""
            yield {
                "type": "chat_complete",
                "data": {"content": "I didn't catch that."},
            }

        mock_agent.handle_message = fake_handle_message

        response = client.post(
            "/chat",
            json={"message": "", "session_id": "test-session"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "I didn't catch that."

    def test_chat_missing_message_field(self) -> None:
        """Missing required 'message' field should return 422."""
        response = client.post(
            "/chat",
            json={"session_id": "test-session"},
        )

        assert response.status_code == 422


# ---------------------------------------------------------------------------
# TestWebSocket
# ---------------------------------------------------------------------------


class TestWebSocket:
    """Tests for the WebSocket /ws endpoint."""

    def test_ws_reset(self) -> None:
        """WebSocket reset message should return a reset confirmation."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "reset"})
            data = ws.receive_json()

            assert data["type"] == "reset"
            assert data["data"]["status"] == "reset"

    def test_ws_set_act(self) -> None:
        """WebSocket set_act message should return confirmation."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json(
                {"type": "set_act", "act": "act1", "wiki_page": "clean"}
            )
            data = ws.receive_json()

            assert data["type"] == "set_act"
            assert data["data"]["act"] == "act1"
            assert data["data"]["wiki_page"] == "clean"

    def test_ws_invalid_json(self) -> None:
        """Sending invalid JSON should return an error event."""
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not valid json")
            data = ws.receive_json()

            assert data["type"] == "error"
            assert "Invalid JSON" in data["data"]["content"]

    def test_ws_unknown_type(self) -> None:
        """Unknown message type should return an error event."""
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "foobar"})
            data = ws.receive_json()

            assert data["type"] == "error"
            assert "Unknown message type" in data["data"]["content"]
