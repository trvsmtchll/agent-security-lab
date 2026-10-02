"""The authenticated MCP server.

Exposes the four tools over streamable HTTP at /mcp, behind the hand-written
verifier and the default-deny scope map. Authentication and authorization run
in an ASGI middleware so failures surface as real HTTP 401/403/503 responses
with the RFC 9728 WWW-Authenticate challenge — independent of FastMCP's
internal JSON-RPC error mapping. RFC 9728 protected-resource metadata and a
health endpoint are served as plain routes.
"""

import json
import logging

import uvicorn
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import authz, verifier
from .config import settings
from .tools import (
    execute_command,
    fetch_webpage,
    github_create_issue,
    query_database,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp-server")

_MCP_PATH = "/mcp"
_RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"
# TM-15: the challenge every unauthenticated/invalid request receives.
_CHALLENGE = (
    'Bearer resource_metadata='
    f'"{settings.canonical_uri.replace("/mcp", "")}{_RESOURCE_METADATA_PATH}", '
    'error="invalid_token"'
)

mcp: FastMCP = FastMCP(
    name="devbot-mcp",
    tools=[query_database, fetch_webpage, execute_command, github_create_issue],
)


@mcp.custom_route(_RESOURCE_METADATA_PATH, methods=["GET"])
async def protected_resource_metadata(request: Request) -> JSONResponse:
    """RFC 9728 protected-resource metadata naming the authorization server."""
    return JSONResponse(
        {
            "resource": settings.canonical_uri,
            "authorization_servers": [settings.oauth_issuer],
            "scopes_supported": sorted(set(authz.TOOL_SCOPES.values())),
            "bearer_methods_supported": ["header"],
        }
    )


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    """Liveness plus the enforcement state the demo panel displays."""
    return JSONResponse(
        {
            "status": "ok",
            "auth_mode": settings.auth_mode,
            "auth_failure_mode": settings.auth_failure_mode,
            "breaker": verifier.breaker_state(),
        }
    )


def _challenge_response(status: int, error: str, description: str) -> JSONResponse:
    """A 401/403 JSON body plus the matching WWW-Authenticate challenge."""
    challenge = (
        'Bearer resource_metadata='
        f'"{settings.canonical_uri.replace("/mcp", "")}{_RESOURCE_METADATA_PATH}", '
        f'error="{error}"'
    )
    return JSONResponse(
        {"error": error, "error_description": description},
        status_code=status,
        headers={"WWW-Authenticate": challenge},
    )


def _bearer_token(scope: dict) -> str:
    """Extract the bearer token from the ASGI scope's Authorization header."""
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            header = value.decode("latin-1")
            if header.lower().startswith("bearer "):
                return header[7:].strip()
    return ""


async def _read_body(receive) -> bytes:
    """Fully buffer an ASGI request body (MCP tool calls are small)."""
    body, more = b"", True
    while more:
        event = await receive()
        body += event.get("body", b"")
        more = event.get("more_body", False)
    return body


def _tool_name(body: bytes) -> str | None:
    """Return the tool name if the JSON-RPC message is a tools/call."""
    try:
        message = json.loads(body)
    except (ValueError, TypeError):
        return None
    if isinstance(message, dict) and message.get("method") == "tools/call":
        return (message.get("params") or {}).get("name")
    return None


class AuthMiddleware:
    """ASGI gate for /mcp: authenticate, then authorize at HTTP level.

    auth_mode=off skips enforcement entirely (Act 1). Otherwise every request
    is verified per request (TM-15); a tools/call is additionally scope-checked
    (TM-14). Non-/mcp paths (metadata, health) pass straight through.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith(_MCP_PATH):
            await self.app(scope, receive, send)
            return
        if settings.auth_mode == "off":
            await self.app(scope, receive, send)
            return

        token = _bearer_token(scope)
        if not token:
            await self._send(send, _challenge_response(401, "invalid_token", "missing bearer token"))
            return
        try:
            claims = verifier.verify_token(token)
        except verifier.InvalidToken as exc:
            await self._send(send, _challenge_response(401, "invalid_token", str(exc)))
            return
        except verifier.AuthUnavailable:
            await self._send(
                send,
                JSONResponse(
                    {"error": "temporarily_unavailable"},
                    status_code=503,
                    headers={"Retry-After": "30"},
                ),
            )
            return

        degraded = bool(claims.pop("_auth_degraded", False))

        body = b""
        if scope["method"] == "POST":
            body = await _read_body(receive)
            tool = _tool_name(body)
            if tool is not None:
                try:
                    authz.require_scope(tool, authz.scopes_from_claims(claims))
                except authz.InsufficientScope as exc:
                    challenge = f'Bearer error="insufficient_scope", scope="{exc.required}"'
                    await self._send(
                        send,
                        JSONResponse(
                            {"error": "insufficient_scope", "scope": exc.required},
                            status_code=403,
                            headers={"WWW-Authenticate": challenge},
                        ),
                    )
                    return
                except authz.UnknownTool:
                    await self._send(
                        send,
                        JSONResponse({"error": "unknown_tool"}, status_code=403),
                    )
                    return

        await self.app(scope, self._replay(body), self._add_degraded(send, degraded))

    @staticmethod
    def _replay(body: bytes):
        """Rebuild a receive() that replays the buffered body once."""
        sent = False

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        return receive

    @staticmethod
    def _add_degraded(send, degraded: bool):
        """Wrap send to add X-Auth-Degraded on the fail_open degraded path."""
        if not degraded:
            return send

        async def wrapped(event):
            if event["type"] == "http.response.start":
                headers = list(event.get("headers", []))
                headers.append((b"x-auth-degraded", b"true"))
                event = {**event, "headers": headers}
            await send(event)

        return wrapped

    @staticmethod
    async def _send(send, response: JSONResponse) -> None:
        await response(
            {"type": "http", "headers": []},
            lambda: {"type": "http.request"},
            send,
        )


def build_app():
    """Build the ASGI app: the MCP streamable-HTTP app behind AuthMiddleware."""
    inner = mcp.http_app(path=_MCP_PATH, transport="streamable-http")
    wrapped = AuthMiddleware(inner)
    # Reason: Starlette discovers the lifespan on the app object, which the
    # plain-class middleware does not expose — carry it through explicitly.
    wrapped.lifespan = inner.lifespan  # type: ignore[attr-defined]
    return wrapped


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)
