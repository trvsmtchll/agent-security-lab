# Demo Walkthrough

Bring the stack up (`docker compose up --build -d`), open the chat UI at
`http://localhost:3010` and the control panel at `http://localhost:3011`, then drive the
three acts from the panel (or the Demo CLI).

## Act 1 — Normal operation
1. Set the panel to **Act 1**.
2. Ask DevBot: *"Look up the deployment runbook and check the database for recent API issues."*
3. The agent fetches the clean runbook and runs a normal read query. Nothing malicious.

## Act 2 — Injection
1. Set the panel to **Act 2** and choose an injection technique.
2. Ask the same question. The wiki now serves a poisoned runbook.
3. Watch the 4-tool kill chain fire automatically: `run_command` (nmap) →
   `query_database` (customers PII) → `push_to_github` / attacker webhook.

## Act 3 — Controls enforced
1. Set the panel to **Act 3**.
2. Ask the same question a third time.
3. Same poisoned page, same attempted chain — every step returns a policy denial instead
   of data. Recon blocked, DB access denied, egress blocked.

The takeaway to narrate: the model and the payload are identical across Acts 2 and 3. Only
the tools' permitted reach changed.

## Auth beats in Act 3 (authenticated MCP)

When the authenticated-MCP layer is in play, Act 3 adds two tool-auth denials alongside the
Sentinel network blocks, so the scope and algorithm lessons are visible even offline
(scripted mode needs no auth server):

- **401 `invalid_token`** — a forged / `alg=none` token is rejected before tool dispatch
  (the RS256 allow-list, RFC 8725).
- **403 `insufficient_scope`** — a valid token scoped to `tools:read` tries
  `execute_command` and is denied; the blast radius is capped by scope (the TM-19 lesson:
  auth narrows reach, it does not stop the hijack).

The canonical live mapping: **Act 1** runs with `AUTH_MODE=off` (control off); **Act 2**
enforces auth with the full scope ceiling, so the injected chain still runs (confused
deputy); **Act 3** narrows the agent's scope to `tools:read`, so the same injected
`execute_command` dies with 403.

## Fail-policy outage demo (live)

`python -m src.cli auth-outage` shows the MCP server's auth mode, failure policy, and
circuit-breaker state, and prints the docker-compose sequence: stop `auth-server` (calls
keep succeeding on cached JWKS — warm cache), restart `mcp-server` cold (`fail_closed` →
503 `Retry-After`; flip `AUTH_FAILURE_MODE=fail_open` → the same call succeeds with
`X-Auth-Degraded: true`), then restart `auth-server` (breaker recovers). This is the
demonstrable fail-open/fail-closed toggle the threat model's fail-policy section describes.

> **Container-boundary nuance (TM-17):** in the default in-process mode the agent's own
> `execute_command` shares the agent container, so a prompt-injected agent could read
> `OAUTH_CLIENT_SECRET` from its environment. The short-lived token is not the crown jewel —
> the client secret is. Moving tools to the MCP server (and keeping the secret off the
> tool-executing workload) is what closes that gap.

## Optional — route MCP through agentgateway

The authenticated MCP server (`services/mcp-server`) is the primary, built-to-be-read
enforcement point. For a production-pattern contrast you can put the open-source
[agentgateway](https://agentgateway.dev) in front of it. It is **off by default**:

```bash
docker compose --profile gateway up        # starts agentgateway on 127.0.0.1:3000
```

Then point the agent at the gateway instead of the backend directly:

```bash
MCP_SERVER_URL=http://agentgateway:3000/mcp   # was http://mcp-server:9000/mcp
```

**What changes:** the gateway serves the RFC 9728 protected-resource metadata, validates
the bearer JWT itself, filters `tools/list` to the tools the token's scopes allow (CEL
rules in `services/agentgateway/config.yaml`, mirroring the server's scope map), and
strips the token before forwarding to the backend.

**What does not change:** it's the *same* tokens the agent already mints, the `aud` stays
`http://mcp-server:9000/mcp`, and `mcp-server` keeps running its own verifier — so a call
that bypasses the gateway and hits the backend directly still faces the full checks
(defense in depth, TM-21).

**One difference worth narrating:** agentgateway is **always fail-closed** with cached
JWKS and has **no fail-open knob**. The lab's own verifier exposes `AUTH_FAILURE_MODE`
(`fail_closed` default, `fail_open` opt-in) precisely so the trade-off is demonstrable —
see the threat model's fail-policy section. That configurability is one reason the
hand-written verifier, not the gateway, is the teaching centerpiece.
