"""Pydantic models for API requests, responses, and WebSocket messages."""

from pydantic import BaseModel
from typing import Literal


class ChatRequest(BaseModel):
    """Incoming chat message from the UI."""
    message: str
    session_id: str = "default"


class ChatResponse(BaseModel):
    """Final chat response."""
    response: str
    session_id: str


class ToolCall(BaseModel):
    """A single tool invocation record for the activity log."""
    tool_name: str
    args: dict
    result: str
    status: Literal["success", "error", "blocked"]
    timestamp: str


class WSMessage(BaseModel):
    """WebSocket message sent to the UI for real-time updates."""
    type: Literal[
        "chat_token",       # Streaming LLM token
        "chat_complete",    # Final response
        "tool_start",       # Tool invocation starting
        "tool_result",      # Tool result
        "terminal_output",  # CLI command output
        "network_event",    # Network connection log
        "state_change",     # Agent state change (normal/compromised/blocked)
        "error",            # Error message
    ]
    data: dict


class DemoState(BaseModel):
    """Current demo state exposed via API."""
    mode: Literal["live", "scripted"]
    wiki_page: str
    act: Literal["idle", "act1", "act2", "act3"]
    agent_state: Literal["normal", "compromised", "blocked"]
    prompt_style: Literal["default", "moderate"] = "default"
    conversation_history: list[dict] = []
    tool_log: list[dict] = []


class ResetResponse(BaseModel):
    """Response from the reset endpoint."""
    status: str
    cleared: list[str]
