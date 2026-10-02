# Architecture & Threat Model

## Components

| Service | Stack | Role in the scenario |
|---------|-------|----------------------|
| `devbot-agent` | FastAPI + LangGraph | The victim: an AI assistant with 4 real tools and a WebSocket stream to the UI |
| `devbot-ui` | React/TS + Vite | Chat surface; shows the conversation and a live tool/terminal/network activity feed |
| `demo-panel` | React/TS + Vite | Operator console that selects the act and injection technique |
| `demo-cli` | Python + Click | Same control surface from the terminal |
| `postgres` | PostgreSQL | `api_docs` (benign runbook metadata) and `customers` (Faker PII) |
| `wiki` | nginx | Serves the clean runbook and the poisoned variants |
| `attacker-server` | FastAPI | Local webhook that records what the agent tried to exfiltrate |
| `auth-server` | FastAPI | OAuth client-credentials issuer + JWKS for the authenticated-MCP path (see below) |
| `mcp-server` | FastMCP | Authenticated MCP resource server: hand-written JWT verifier + per-tool scope map |
| `agentgateway` | agentgateway (opt-in) | Optional gateway in front of `mcp-server` — defense-in-depth contrast, off by default |

## Trust boundaries

The agent treats **tool output as trusted input to its own reasoning**. That is the flaw
the demo exercises: content fetched from the wiki (`fetch_webpage`) flows straight into
the model's context, so instructions hidden in a wiki page become instructions to the
agent. The three injection techniques differ only in how they disguise that content:

- **Semantic camouflage** — malicious steps framed as routine compliance checks.
- **Authority escalation** — steps framed as directives from a trusted authority.
- **Incremental normalization** — a benign-looking sequence that escalates step by step.

## Where the controls live

The Act 3 defense is not a smarter prompt — it is the assumption that the tools' reach is
constrained by policy. Mapped to the kill chain:

1. **Network recon** is stopped by default-deny east-west segmentation.
2. **PII access** is stopped by per-workload credentials and least-privilege grants, so a
   dev-facing agent simply cannot read the customers table.
3. **Exfiltration** is stopped by an egress allow-list — the agent has no route to
   arbitrary internet destinations or unapproved repos.
4. **The injection itself** is mitigated upstream by treating fetched content as
   untrusted and screening tool output before it re-enters the model's context.

`scripted.py` encodes both the compromised and the defended flows deterministically so the
contrast is reproducible without depending on a model's nondeterminism.

## The authenticated-MCP control (optional, `MCP_ENABLED`)

A second, orthogonal control moves the four tools behind an authenticated MCP server
(`services/mcp-server`) fronted by an OAuth client-credentials issuer
(`services/auth-server`). The agent must present a short-lived, scope-bounded JWT — minted
by the issuer, verified against its JWKS — before any tool runs. This adds a **token
boundary** to the kill chain: each tool requires a specific scope (`tools:read` for
query/fetch, `tools:execute` for shell, `tools:write` for GitHub), so a token narrowed to
`tools:read` cannot reach `execute_command` at all (403 `insufficient_scope`), and a forged
or `alg=none` token is rejected before dispatch (401 `invalid_token`). Full design,
fail-open/fail-closed policy, and the STRIDE table are in
[`docs/plans/authenticated-mcp/`](plans/authenticated-mcp/THREAT_MODEL.md).

**Honest framing (TM-19):** authentication narrows *what a hijacked agent can reach* — it
caps the blast radius by scope — but it does **not** stop the hijack. A prompt-injected
agent holding a valid token is a confused deputy: within its granted scopes, its tool calls
still succeed. That is why the lab keeps auth as one layer among segmentation, least
privilege, and egress control, not a replacement for them.
