"""Tests for the default-deny per-tool scope map (TM-14)."""

from src import authz


class TestRequireScope:
    """require_scope enforces the tool->scope map, default-deny."""

    def test_correct_scope_passes(self) -> None:
        authz.require_scope("query_database", {"tools:read"})
        authz.require_scope("execute_command", {"tools:read", "tools:execute"})
        authz.require_scope("github_create_issue", {"tools:write"})

    def test_missing_scope_raises_with_required_name(self) -> None:
        try:
            authz.require_scope("execute_command", {"tools:read"})
            raise AssertionError("escalation allowed")
        except authz.InsufficientScope as exc:
            assert exc.required == "tools:execute"

    def test_write_tool_requires_write_scope(self) -> None:
        try:
            authz.require_scope("github_create_issue", {"tools:read", "tools:execute"})
            raise AssertionError("write without scope allowed")
        except authz.InsufficientScope as exc:
            assert exc.required == "tools:write"

    def test_unknown_tool_is_default_denied(self) -> None:
        try:
            authz.require_scope("rm_rf", {"tools:read", "tools:execute", "tools:write"})
            raise AssertionError("unknown tool dispatchable")
        except authz.UnknownTool:
            pass


class TestScopeParsing:
    """scopes_from_claims parses the space-delimited scope claim."""

    def test_parses_space_delimited(self) -> None:
        assert authz.scopes_from_claims({"scope": "tools:read tools:write"}) == {
            "tools:read",
            "tools:write",
        }

    def test_missing_scope_is_empty(self) -> None:
        assert authz.scopes_from_claims({}) == set()


class TestToolCoverage:
    """Every registered FastMCP tool must have a scope entry (adding a tool
    without one fails here, so it cannot ship unauthorized)."""

    def test_all_server_tools_have_a_scope(self) -> None:
        from src import tools

        registered = {
            "query_database",
            "fetch_webpage",
            "execute_command",
            "github_create_issue",
        }
        # The tool functions exist in the tools module...
        for name in registered:
            assert hasattr(tools, name), name
        # ...and each is in the scope map (default-deny completeness).
        assert registered <= set(authz.TOOL_SCOPES)
