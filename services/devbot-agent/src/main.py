"""FastAPI application with REST endpoints and WebSocket for real-time streaming.

Wraps the DevBotAgent and exposes it via REST and WebSocket. The demo CLI
(Task 13) and demo panel (Task 14) call these endpoints. The React UI
(Tasks 10-12) connects via WebSocket.
"""

import json
from typing import Literal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import DevBotAgent
from .config import settings
from .models import ChatRequest, ChatResponse, DemoState, ResetResponse


# ---------------------------------------------------------------------------
# Pydantic request model for set-act endpoint
# ---------------------------------------------------------------------------


class SetActRequest(BaseModel):
    """Request body for the /set-act endpoint.

    Args:
        act: The demo act to switch to.
        injection_technique: Which poisoned wiki variant to use for act2/act3.
    """

    act: Literal["idle", "act1", "act2", "act3"]
    injection_technique: Literal["v2", "v3", "v4"] = "v2"


# ---------------------------------------------------------------------------
# Application setup
# ---------------------------------------------------------------------------

app = FastAPI(title="DevBot Agent", version="1.0.0")

# CORS middleware — allow all origins for demo purposes
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Single module-level agent instance shared across all requests
agent = DevBotAgent()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    """Health check endpoint.

    Returns:
        dict: Status info including demo mode and LLM provider.
    """
    return {
        "status": "ok",
        "mode": settings.demo_mode,
        "provider": settings.llm_provider,
        "prompt_style": settings.prompt_style,
    }


@app.post("/reset", response_model=ResetResponse)
async def reset() -> ResetResponse:
    """Reset the agent to its default state.

    Returns:
        ResetResponse: Confirmation with list of cleared fields.
    """
    agent.reset()
    return ResetResponse(
        status="reset",
        cleared=[
            "conversation_history",
            "current_step",
            "current_act",
            "agent_state",
            "tool_log",
            "wiki_page",
        ],
    )


@app.get("/state", response_model=DemoState)
async def get_state() -> DemoState:
    """Return the current demo state.

    Returns:
        DemoState: Current mode, act, agent state, conversation history,
            and tool log.
    """
    return DemoState(
        mode=settings.demo_mode,
        wiki_page=agent._wiki_page,
        act=agent.current_act,
        agent_state=agent.agent_state,
        prompt_style=settings.prompt_style,
        conversation_history=agent.conversation_history,
        tool_log=agent.tool_log,
    )


def _apply_auth_act_mapping(act: str) -> None:
    """Apply the live authenticated-MCP act mapping (no-op in scripted mode).

    Scripted mode is unaffected — the Act 3 flow already carries the 401/403
    denial beats. Only the agent-controllable half of the canonical mapping
    lives here: the scope the agent requests. Act 3 narrows the token to
    tools:read so the injected execute_command is denied 403 insufficient_scope
    (TM-14); Act 1/2 keep the full ceiling (Act 2 is the TM-19 confused-deputy
    case — auth passes and the kill chain still runs). The mcp-server's
    AUTH_MODE (off in Act 1) is a container-level setting, documented in
    DEMO.md, not flipped from the agent.
    """
    if not settings.mcp_enabled:
        return
    if act == "act3":
        settings.oauth_scope = "tools:read"
    else:
        settings.oauth_scope = "tools:read tools:execute tools:write"


@app.post("/set-act")
async def set_act(request: SetActRequest) -> dict:
    """Set the current demo act with auto-configured prompt style and wiki page.

    Auto-configuration per act:
      - act1/idle: clean wiki, default prompt
      - act2: poisoned-{technique} wiki, moderate prompt
      - act3: poisoned-{technique} wiki, moderate prompt (tools blocked)

    Args:
        request: SetActRequest with act and injection_technique fields.

    Returns:
        dict: Confirmation of the new act, wiki page, prompt style, and technique.
    """
    # Reason: Auto-configure prompt style and wiki page per act so the
    # demo panel only needs to send the act and technique.
    technique = request.injection_technique
    if request.act in ("act2", "act3"):
        wiki_page = f"poisoned-{technique}"
        prompt_style = "moderate"
    else:
        wiki_page = "clean"
        prompt_style = "default"

    agent.set_act(request.act)
    agent.set_wiki_page(wiki_page)
    settings.prompt_style = prompt_style
    _apply_auth_act_mapping(request.act)

    return {
        "status": "ok",
        "act": request.act,
        "wiki_page": wiki_page,
        "prompt_style": prompt_style,
        "injection_technique": technique,
    }


class SetPromptStyleRequest(BaseModel):
    """Request body for the /set-prompt-style endpoint.

    Args:
        style: The prompt style to apply.
    """

    style: Literal["default", "moderate"]


@app.post("/set-prompt-style")
async def set_prompt_style(request: SetPromptStyleRequest) -> dict:
    """Dynamically change the prompt style at runtime without restarting.

    Args:
        request: SetPromptStyleRequest with the desired style.

    Returns:
        dict: Confirmation of the new prompt style.
    """
    settings.prompt_style = request.style
    return {"status": "ok", "prompt_style": request.style}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat message and return the final response.

    Iterates through all events from agent.handle_message() and returns
    the last chat_complete content as the response.

    Args:
        request: ChatRequest with message and session_id.

    Returns:
        ChatResponse: The final assistant response.
    """
    last_content = ""
    async for event in agent.handle_message(request.message):
        if event.get("type") == "chat_complete":
            last_content = event.get("data", {}).get("content", "")

    return ChatResponse(
        response=last_content,
        session_id=request.session_id,
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for real-time streaming of agent events.

    Accepts JSON messages with the following types:
    - {"type": "chat", "message": "..."} — Send a chat message
    - {"type": "reset"} — Reset the agent state
    - {"type": "set_act", "act": "...", "wiki_page": "..."} — Set the demo act

    Streams back all events from agent.handle_message() as JSON.
    """
    await websocket.accept()
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "data": {"content": "Invalid JSON"}}
                )
                continue

            msg_type = data.get("type")

            if msg_type == "chat":
                message = data.get("message", "")
                async for event in agent.handle_message(message):
                    await websocket.send_json(event)

            elif msg_type == "reset":
                agent.reset()
                await websocket.send_json(
                    {"type": "reset", "data": {"status": "reset"}}
                )

            elif msg_type == "set_act":
                act = data.get("act", "idle")
                technique = data.get("injection_technique", "v2")
                # Reason: Same auto-config logic as the REST endpoint
                if act in ("act2", "act3"):
                    wiki_page = f"poisoned-{technique}"
                    prompt_style = "moderate"
                else:
                    wiki_page = "clean"
                    prompt_style = "default"
                agent.set_act(act)
                agent.set_wiki_page(wiki_page)
                settings.prompt_style = prompt_style
                _apply_auth_act_mapping(act)
                await websocket.send_json(
                    {
                        "type": "set_act",
                        "data": {
                            "status": "ok",
                            "act": act,
                            "wiki_page": wiki_page,
                            "prompt_style": prompt_style,
                            "injection_technique": technique,
                        },
                    }
                )

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "data": {
                            "content": f"Unknown message type: {msg_type}"
                        },
                    }
                )

    except WebSocketDisconnect:
        pass
