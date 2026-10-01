"""Tests for scripted mode flows.

Verifies that SCRIPTED_FLOWS contains valid act definitions and that
get_scripted_response returns the correct step dicts or None for
invalid inputs.
"""

import pytest
from src.scripted import SCRIPTED_FLOWS, get_scripted_response


# ---------------------------------------------------------------------------
# TestScriptedFlowStructure
# ---------------------------------------------------------------------------


class TestScriptedFlowStructure:
    """Tests for the overall structure of SCRIPTED_FLOWS."""

    def test_all_acts_have_flows(self) -> None:
        """SCRIPTED_FLOWS must contain act1, act2, and act3."""
        assert "act1" in SCRIPTED_FLOWS
        assert "act2" in SCRIPTED_FLOWS
        assert "act3" in SCRIPTED_FLOWS

    def test_act1_has_two_steps(self) -> None:
        """Act 1 (normal usage) should have exactly 2 steps."""
        assert len(SCRIPTED_FLOWS["act1"]) == 2

    def test_act2_has_four_steps(self) -> None:
        """Act 2 (compromised, attack succeeds) should have exactly 4 steps."""
        assert len(SCRIPTED_FLOWS["act2"]) == 4

    def test_act3_step_count(self) -> None:
        """Act 3 has 4 Sentinel/narrative steps plus 2 MCP auth-denial beats."""
        assert len(SCRIPTED_FLOWS["act3"]) == 6

    def test_all_steps_have_required_keys(self) -> None:
        """Every step in every act must have response, tool_calls, and follow_up."""
        for act_name, steps in SCRIPTED_FLOWS.items():
            for i, step in enumerate(steps):
                assert "response" in step, f"{act_name} step {i} missing 'response'"
                assert "tool_calls" in step, f"{act_name} step {i} missing 'tool_calls'"
                assert "follow_up" in step, f"{act_name} step {i} missing 'follow_up'"

    def test_all_tool_calls_have_tool_and_args(self) -> None:
        """Every tool_call dict must have 'tool' and 'args' keys."""
        for act_name, steps in SCRIPTED_FLOWS.items():
            for i, step in enumerate(steps):
                for j, tc in enumerate(step["tool_calls"]):
                    assert "tool" in tc, (
                        f"{act_name} step {i} tool_call {j} missing 'tool'"
                    )
                    assert "args" in tc, (
                        f"{act_name} step {i} tool_call {j} missing 'args'"
                    )


# ---------------------------------------------------------------------------
# TestAct1Responses
# ---------------------------------------------------------------------------


class TestAct1Responses:
    """Tests for Act 1 (normal usage) scripted responses."""

    def test_act1_happy_path_response(self) -> None:
        """Act 1 step 0 should return a valid response about the wiki."""
        step = get_scripted_response("show me the wiki", "act1", 0)
        assert step is not None
        assert isinstance(step["response"], str)
        assert len(step["response"]) > 0
        assert step["tool_calls"][0]["tool"] == "fetch_webpage"
        assert "runbook.html" in step["tool_calls"][0]["args"]["url"]

    def test_act1_step1_queries_database(self) -> None:
        """Act 1 step 1 should query the api_docs INFORMATION_SCHEMA."""
        step = get_scripted_response("what's the db schema?", "act1", 1)
        assert step is not None
        assert step["tool_calls"][0]["tool"] == "query_database"
        assert "information_schema" in step["tool_calls"][0]["args"]["query"].lower()
        assert step["tool_calls"][0]["args"]["database"] == "api_docs"

    def test_act1_has_no_compromised_flag(self) -> None:
        """Act 1 steps should not set compromised or blocked flags."""
        for i in range(len(SCRIPTED_FLOWS["act1"])):
            step = get_scripted_response("msg", "act1", i)
            assert step is not None
            assert step.get("compromised") is not True
            assert step.get("blocked") is not True


# ---------------------------------------------------------------------------
# TestAct2Responses
# ---------------------------------------------------------------------------


class TestAct2Responses:
    """Tests for Act 2 (compromised agent, attack succeeds)."""

    def test_act2_attack_has_tool_calls(self) -> None:
        """Act 2 step 0 should have tool_calls for the poisoned wiki page."""
        step = get_scripted_response("show me the runbook", "act2", 0)
        assert step is not None
        assert len(step["tool_calls"]) > 0
        assert step["tool_calls"][0]["tool"] == "fetch_webpage"
        assert "runbook-poisoned" in step["tool_calls"][0]["args"]["url"]

    def test_act2_step0_sets_compromised(self) -> None:
        """Act 2 step 0 should set the compromised flag."""
        step = get_scripted_response("msg", "act2", 0)
        assert step is not None
        assert step.get("compromised") is True

    def test_act2_nmap_step_auto_advances(self) -> None:
        """Act 2 step 1 (nmap) should auto-advance."""
        step = get_scripted_response("msg", "act2", 1)
        assert step is not None
        assert step.get("auto_advance") is True
        assert step["tool_calls"][0]["tool"] == "execute_command"
        assert "nmap" in step["tool_calls"][0]["args"]["command"]

    def test_act2_exfil_step_creates_github_issue(self) -> None:
        """Act 2 step 3 should create a GitHub issue for exfiltration."""
        step = get_scripted_response("msg", "act2", 3)
        assert step is not None
        assert step["tool_calls"][0]["tool"] == "github_create_issue"
        assert "{date}" in step["tool_calls"][0]["args"]["title"]
        assert "{exfil_data}" in step["tool_calls"][0]["args"]["body"]

    def test_act2_steps_are_not_blocked(self) -> None:
        """Act 2 attacks succeed, so no step should carry the `blocked` flag.

        The recon step still carries a canned `override_result` for deterministic
        nmap output; being blocked is what distinguishes Act 3, not that.
        """
        for i in range(len(SCRIPTED_FLOWS["act2"])):
            step = get_scripted_response("msg", "act2", i)
            assert step is not None
            assert step.get("blocked") is not True


# ---------------------------------------------------------------------------
# TestAct3Responses
# ---------------------------------------------------------------------------


class TestAct3Responses:
    """Tests for Act 3 (Sentinel blocks the attack)."""

    def test_act3_blocked_has_override_result(self) -> None:
        """Act 3 step 1 (nmap) should have an override_result with Sentinel denial."""
        step = get_scripted_response("msg", "act3", 1)
        assert step is not None
        assert "override_result" in step
        assert "Sentinel" in step["override_result"]
        assert "Policy Denied" in step["override_result"]

    def test_act3_step0_sets_compromised(self) -> None:
        """Act 3 step 0 should still set compromised (agent is fooled)."""
        step = get_scripted_response("msg", "act3", 0)
        assert step is not None
        assert step.get("compromised") is True

    def test_act3_all_attack_steps_blocked(self) -> None:
        """Act 3 steps 1-3 should all have blocked=True."""
        for i in [1, 2, 3]:
            step = get_scripted_response("msg", "act3", i)
            assert step is not None
            assert step.get("blocked") is True, f"Act 3 step {i} should be blocked"

    def test_act3_github_exfil_blocked_by_suricata(self) -> None:
        """Act 3 step 3 (GitHub exfil) should mention Suricata in override."""
        step = get_scripted_response("msg", "act3", 3)
        assert step is not None
        assert "Suricata" in step["override_result"]
        assert "Egress" in step["override_result"]

    def test_act3_db_query_blocked_cross_vpc(self) -> None:
        """Act 3 step 2 (DB query) should mention cross-VPC denial."""
        step = get_scripted_response("msg", "act3", 2)
        assert step is not None
        assert "Cross-VPC" in step["override_result"]


# ---------------------------------------------------------------------------
# TestGetScriptedResponse — Edge & Failure Cases
# ---------------------------------------------------------------------------


class TestGetScriptedResponse:
    """Tests for get_scripted_response boundary conditions."""

    def test_unknown_act_returns_none(self) -> None:
        """An unknown act name should return None."""
        result = get_scripted_response("hello", "act99", 0)
        assert result is None

    def test_negative_step_returns_none(self) -> None:
        """A negative step index should return None."""
        result = get_scripted_response("hello", "act1", -1)
        assert result is None

    def test_step_out_of_range_returns_none(self) -> None:
        """A step index beyond the flow length should return None."""
        result = get_scripted_response("hello", "act1", 100)
        assert result is None

    def test_empty_act_returns_none(self) -> None:
        """An empty act name should return None."""
        result = get_scripted_response("hello", "", 0)
        assert result is None

    def test_valid_step_returns_dict(self) -> None:
        """A valid act + step should return a dict, not None."""
        result = get_scripted_response("anything", "act1", 0)
        assert result is not None
        assert isinstance(result, dict)
