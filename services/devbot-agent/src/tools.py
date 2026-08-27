"""MCP tool functions for DevBot agent.

Each tool is a real, executable function. In the demo, these are called
by the LangGraph agent based on LLM decisions (or scripted responses).
"""

import subprocess
import psycopg2
import httpx
from typing import Optional
from .config import settings


def query_database(query: str, database: str = "api_docs") -> str:
    """Execute a SQL query against the specified database.

    Args:
        query: SQL query string to execute.
        database: Which database to query — "api_docs" or "customers".

    Returns:
        str: Formatted query results or error message.
    """
    if not query.strip():
        return "Error: Empty query string."

    db_url = (
        settings.database_url
        if database == "api_docs"
        else settings.customers_database_url
    )

    try:
        with psycopg2.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(query)
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    header = " | ".join(columns)
                    separator = "-+-".join("-" * len(c) for c in columns)
                    data_rows = [" | ".join(str(v) for v in row) for row in rows]
                    return f"{header}\n{separator}\n" + "\n".join(data_rows)
                else:
                    return f"Query executed successfully. Rows affected: {cur.rowcount}"
    except Exception as e:
        return f"Error executing query: {str(e)}"


def fetch_webpage(url: str) -> str:
    """Fetch the content of a webpage and return its text.

    Args:
        url: The URL to fetch.

    Returns:
        str: The page content or error message.
    """
    if not url.strip():
        return "Error: Empty URL."

    try:
        response = httpx.get(url, timeout=10.0, follow_redirects=True)
        response.raise_for_status()
        return response.text
    except Exception as e:
        return f"Error fetching webpage: {str(e)}"


def execute_command(command: str, timeout: int = 30) -> str:
    """Execute a shell command and return its output.

    Args:
        command: Shell command string to execute.
        timeout: Maximum seconds to wait for command completion.

    Returns:
        str: Command stdout/stderr or error message.
    """
    if not command.strip():
        return "Error: Empty command."

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout
        if result.stderr:
            output += f"\nSTDERR: {result.stderr}"
        if result.returncode != 0:
            output += f"\n[Exit code: {result.returncode}]"
        return output if output.strip() else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Command timed out after {timeout} seconds."
    except Exception as e:
        return f"Error executing command: {str(e)}"


def github_create_issue(title: str, body: str = "", repo: Optional[str] = None) -> str:
    """Create a GitHub issue on the configured repository.

    Args:
        title: Issue title.
        body: Issue body content.
        repo: Repository in "owner/repo" format. Defaults to GITHUB_EXFIL_REPO.

    Returns:
        str: Issue URL or error message.
    """
    if not title.strip():
        return "Error: Empty issue title."

    repo = repo or settings.github_exfil_repo
    pat = settings.github_pat

    if not pat:
        return "Error: GITHUB_PAT not configured."

    try:
        response = httpx.post(
            f"https://api.github.com/repos/{repo}/issues",
            headers={
                "Authorization": f"token {pat}",
                "Accept": "application/vnd.github.v3+json",
            },
            json={"title": title, "body": body},
            timeout=15.0,
        )
        if response.status_code == 201:
            data = response.json()
            return f"Issue created: {data['html_url']}"
        else:
            return f"GitHub API error ({response.status_code}): {response.text}"
    except Exception as e:
        return f"Error creating GitHub issue: {str(e)}"
