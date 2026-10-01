"""Demo orchestration CLI.

Usage:
    python -m src.cli reset       -- Reset all state
    python -m src.cli act1        -- Set up Act 1 (happy path)
    python -m src.cli act2        -- Set up Act 2 (attack)
    python -m src.cli act3        -- Set up Act 3 (blocked)
    python -m src.cli deepseek    -- Trigger DeepSeek test call
    python -m src.cli splunk-clear -- Clear alert state
    python -m src.cli status      -- Show current state
"""

import click
import httpx
from rich.console import Console
from rich.table import Table

console = Console()

AGENT_URL = "http://devbot-agent:8000"
ATTACKER_URL = "http://attacker-server:8080"
MCP_URL = "http://mcp-server:9000"

# Reason: Timeout for HTTP requests to avoid blocking indefinitely during demos
REQUEST_TIMEOUT = 10.0


def _post(url: str, json: dict | None = None) -> dict:
    """Send a POST request and return parsed JSON.

    Args:
        url: Full URL to POST to.
        json: Optional JSON body.

    Returns:
        dict: Parsed JSON response.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.post(url, json=json, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _get(url: str) -> dict:
    """Send a GET request and return parsed JSON.

    Args:
        url: Full URL to GET.

    Returns:
        dict: Parsed JSON response.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _delete(url: str) -> dict:
    """Send a DELETE request and return parsed JSON.

    Args:
        url: Full URL to DELETE.

    Returns:
        dict: Parsed JSON response.

    Raises:
        httpx.HTTPError: On network or HTTP errors.
    """
    response = httpx.delete(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


@click.group()
@click.option("--agent-url", default=AGENT_URL, envvar="AGENT_URL",
              help="DevBot agent API URL.")
@click.option("--attacker-url", default=ATTACKER_URL, envvar="ATTACKER_URL",
              help="Attacker server API URL.")
@click.pass_context
def cli(ctx: click.Context, agent_url: str, attacker_url: str) -> None:
    """Operation Shadow Agent -- Demo Orchestration CLI."""
    ctx.ensure_object(dict)
    ctx.obj["agent_url"] = agent_url
    ctx.obj["attacker_url"] = attacker_url


@cli.command()
@click.pass_context
def reset(ctx: click.Context) -> None:
    """Reset all demo state to clean starting point."""
    agent_url = ctx.obj["agent_url"]
    attacker_url = ctx.obj["attacker_url"]

    console.print("[bold yellow]Resetting demo state...[/bold yellow]")

    # Reset agent state
    try:
        result = _post(f"{agent_url}/reset")
        cleared = ", ".join(result.get("cleared", []))
        console.print(f"  [green]Agent reset:[/green] cleared {cleared}")
    except Exception as exc:
        console.print(f"  [red]Agent reset failed:[/red] {exc}")

    # Clear attacker exfil data
    try:
        result = _delete(f"{attacker_url}/exfil")
        console.print(
            f"  [green]Attacker server:[/green] {result.get('status', 'unknown')}"
        )
    except Exception as exc:
        console.print(f"  [red]Attacker server clear failed:[/red] {exc}")

    console.print("[bold green]Reset complete.[/bold green]")


def _set_act(ctx: click.Context, act: str, wiki_page: str) -> None:
    """Set the demo act on the agent.

    Args:
        ctx: Click context with agent_url in obj.
        act: The act identifier (act1, act2, act3).
        wiki_page: Which wiki page variant to use (clean or poisoned).
    """
    agent_url = ctx.obj["agent_url"]

    console.print(
        f"[bold yellow]Setting {act} (wiki_page={wiki_page})...[/bold yellow]"
    )

    try:
        result = _post(
            f"{agent_url}/set-act",
            json={"act": act, "wiki_page": wiki_page},
        )
        console.print(
            f"  [green]Act:[/green] {result.get('act')}  "
            f"[green]Wiki:[/green] {result.get('wiki_page')}"
        )
        console.print(f"[bold green]{act} is ready.[/bold green]")
    except Exception as exc:
        console.print(f"  [red]Failed to set act:[/red] {exc}")


@cli.command()
@click.pass_context
def act1(ctx: click.Context) -> None:
    """Set up Act 1 -- The Happy Path."""
    _set_act(ctx, act="act1", wiki_page="clean")


@cli.command()
@click.pass_context
def act2(ctx: click.Context) -> None:
    """Set up Act 2 -- The Attack."""
    _set_act(ctx, act="act2", wiki_page="poisoned")


@cli.command()
@click.pass_context
def act3(ctx: click.Context) -> None:
    """Set up Act 3 -- The Fix (Sentinel blocks everything)."""
    _set_act(ctx, act="act3", wiki_page="poisoned")


@cli.command()
@click.pass_context
def deepseek(ctx: click.Context) -> None:
    """Trigger a test call to api.deepseek.com."""
    agent_url = ctx.obj["agent_url"]

    console.print(
        "[bold yellow]Sending DeepSeek test message to agent...[/bold yellow]"
    )

    try:
        result = _post(
            f"{agent_url}/chat",
            json={
                "message": (
                    "Can you make a quick test call to api.deepseek.com "
                    "to check if it is reachable?"
                ),
                "session_id": "demo-cli",
            },
        )
        response_text = result.get("response", "(no response)")
        console.print(f"  [green]Agent response:[/green] {response_text}")
    except Exception as exc:
        console.print(f"  [red]DeepSeek test call failed:[/red] {exc}")


@cli.command("splunk-clear")
@click.pass_context
def splunk_clear(ctx: click.Context) -> None:
    """Clear alert state (placeholder)."""
    console.print(
        "[bold cyan]Splunk alert state is managed externally.[/bold cyan]\n"
        "  Use the Splunk UI or REST API to clear alerts.\n"
        "  Typically: POST /services/alerts/fired_alerts/<alert>/clear"
    )


@cli.command("auth-outage")
@click.option("--mcp-url", default=MCP_URL, envvar="MCP_URL",
              help="MCP server base URL.")
@click.pass_context
def auth_outage(ctx: click.Context, mcp_url: str) -> None:
    """Show MCP auth fail-policy state and the JWKS-outage demo sequence.

    Reads mcp-server /health (auth mode, failure policy, circuit-breaker
    state) so an operator can watch the fail_closed/fail_open contrast while
    taking the issuer down and back up. The outage itself is driven with
    docker compose (steps printed below); this command is the read-only probe.
    """
    table = Table(title="MCP Auth Fail-Policy State", show_header=True)
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    try:
        health = _get(f"{mcp_url}/health")
        table.add_row("Status", health.get("status", "unknown"))
        table.add_row("Auth mode", health.get("auth_mode", "unknown"))
        table.add_row("Failure policy", health.get("auth_failure_mode", "unknown"))
        table.add_row("Circuit breaker", health.get("breaker", "unknown"))
    except Exception as exc:
        table.add_row("Error", f"[red]{exc}[/red]")

    console.print(table)
    console.print(
        "\n[bold]JWKS-outage demo (run these with docker compose):[/bold]\n"
        "  1. JWKS_CACHE_TTL=60; docker compose stop auth-server\n"
        "     -> tool calls still succeed on cached keys (warm cache, TM-08).\n"
        "  2. docker compose restart mcp-server  (cold cache)\n"
        "     -> fail_closed: 503 Retry-After; set AUTH_FAILURE_MODE=fail_open\n"
        "        and restart -> same call succeeds with X-Auth-Degraded: true.\n"
        "  3. docker compose start auth-server\n"
        "     -> breaker half-opens then closes; normal 401/403 resume.\n"
        "  Re-run `auth-outage` at each step to watch the breaker state."
    )


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current demo state."""
    agent_url = ctx.obj["agent_url"]
    attacker_url = ctx.obj["attacker_url"]

    # --- Agent state ---
    agent_table = Table(title="Agent State", show_header=True)
    agent_table.add_column("Field", style="cyan")
    agent_table.add_column("Value", style="white")

    try:
        state = _get(f"{agent_url}/state")
        agent_table.add_row("Mode", state.get("mode", "unknown"))
        agent_table.add_row("Act", state.get("act", "unknown"))
        agent_table.add_row("Wiki Page", state.get("wiki_page", "unknown"))
        agent_table.add_row("Agent State", state.get("agent_state", "unknown"))
        agent_table.add_row(
            "Conversation Length",
            str(len(state.get("conversation_history", []))),
        )
        agent_table.add_row(
            "Tool Calls",
            str(len(state.get("tool_log", []))),
        )
    except Exception as exc:
        agent_table.add_row("Error", f"[red]{exc}[/red]")

    console.print(agent_table)
    console.print()

    # --- Attacker server state ---
    exfil_table = Table(title="Attacker Server (Exfil Data)", show_header=True)
    exfil_table.add_column("Field", style="cyan")
    exfil_table.add_column("Value", style="white")

    try:
        exfil = _get(f"{attacker_url}/exfil")
        count = exfil.get("count", 0)
        exfil_table.add_row("Total Payloads", str(count))

        entries = exfil.get("entries", [])
        for i, entry in enumerate(entries, start=1):
            exfil_table.add_row(
                f"  [{i}] Title",
                entry.get("title", "(none)"),
            )
            exfil_table.add_row(
                f"  [{i}] Size",
                f"{entry.get('size_bytes', 0)} bytes",
            )
            exfil_table.add_row(
                f"  [{i}] Time",
                entry.get("timestamp", "unknown"),
            )
    except Exception as exc:
        exfil_table.add_row("Error", f"[red]{exc}[/red]")

    console.print(exfil_table)


if __name__ == "__main__":
    cli()
