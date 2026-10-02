"""Per-tool authorization: a default-deny scope map (TM-14).

A validated token proves *who* is calling; this module decides *what* that
token's scopes permit. A tool missing from TOOL_SCOPES is never dispatchable.
"""


class UnknownTool(Exception):
    """Tool is not in the scope map — default-deny (never dispatchable)."""


class InsufficientScope(Exception):
    """Token lacks the scope the tool requires — the server maps this to 403.

    Attributes:
        required (str): The scope the caller is missing, named in the
            WWW-Authenticate challenge.
    """

    def __init__(self, required: str) -> None:
        self.required = required
        super().__init__(f"insufficient_scope: {required}")


# Reason: default-deny — a tool missing from this map is never dispatchable.
TOOL_SCOPES: dict[str, str] = {
    "query_database": "tools:read",
    "fetch_webpage": "tools:read",
    "execute_command": "tools:execute",
    "github_create_issue": "tools:write",
}


def require_scope(tool_name: str, granted_scopes: set[str]) -> None:
    """Raise unless the token carries the tool's required scope.

    Args:
        tool_name (str): Canonical tool name being dispatched.
        granted_scopes (set[str]): Scopes parsed from the validated token.

    Raises:
        UnknownTool: If the tool is not in TOOL_SCOPES (default-deny).
        InsufficientScope: If the required scope is absent.
    """
    if tool_name not in TOOL_SCOPES:
        raise UnknownTool(tool_name)
    required = TOOL_SCOPES[tool_name]
    if required not in granted_scopes:
        raise InsufficientScope(required)


def scopes_from_claims(claims: dict) -> set[str]:
    """Parse the space-delimited `scope` claim into a set."""
    return set(str(claims.get("scope", "")).split())
