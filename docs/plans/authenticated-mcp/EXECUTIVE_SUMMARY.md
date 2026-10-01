# Authenticated MCP Server — Executive Summary

**For:** a non-implementer deciding whether this is the right design.
**Status:** implemented on branch `feature/authenticated-mcp`. Companion docs:
[THREAT_MODEL.md](THREAT_MODEL.md), [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).

## What was built

The four DevBot tools (SQL, HTTP fetch, shell, GitHub) can now run behind an
**authenticated MCP server** instead of only in-process. Two small, readable
Python services were added:

- **`auth-server`** — a ~100-line FastAPI OAuth 2.1 client-credentials issuer: it mints
  short-lived (300 s) RS256 JWTs, publishes a JWKS, serves discovery metadata, and (in the
  lab only) can mint deliberately broken tokens for negative tests.
- **`mcp-server`** — a FastMCP streamable-HTTP server wrapping the four tools behind a
  **hand-written ~150-line JWT/JWKS verifier** and a default-deny per-tool scope map, with
  RFC 9728 protected-resource metadata and a `/health` endpoint.

The DevBot agent gained an OAuth token client and a lazy MCP transport, gated by
`MCP_ENABLED` (**default off**, so the scripted offline demo and the full existing test
suite are untouched). The three-act demo now also teaches auth: Act 1 unauthenticated,
Act 2 the confused-deputy case (auth passes, the injected chain still runs), Act 3
scope-narrowed so the same attack dies with `403 insufficient_scope`.

## Why an in-framework verifier, not a gateway or a real IdP

This lab is *built to be read*. The hand-written verifier puts every security decision —
the RS256 allow-list, `iss`/`aud`/`exp`/`nbf`/`typ` checks, kid-sanitized JWKS lookup,
caching, and the one fail-open/fail-closed branch — in plain Python a student can read,
break, and step through. A production gateway or IdP would hide exactly the checks the lab
exists to teach. The optional [agentgateway](https://agentgateway.dev) profile is included
as a *contrast* (same tokens, enforcement in an opaque Rust binary, no fail-open knob), not
as the primary path. A heavy IdP (Keycloak/Hydra/Dex) was rejected for the same reason,
plus container weight.

## The fail-open / fail-closed trade

One env var, `AUTH_FAILURE_MODE`, consulted at exactly one point: when a token's key cannot
be resolved because the JWKS is unreachable. Every other failure (bad signature, `iss`,
`aud`, `alg`, `exp`) is rejected in both modes.

| JWKS/issuer state | `fail_closed` (default) | `fail_open` |
|---|---|---|
| Reachable, or keys cached (warm) | Normal verification | Normal verification |
| Unreachable + no cached key (cold) | **503 + `Retry-After`** | Accept iff `iss`/`aud`/`exp`/`nbf`/`typ` pass; loud audit log + `X-Auth-Degraded: true` |
| Expired / invalid token | 401 | 401 |

Fail-closed is the default (OWASP "fail securely"); fail-open exists only as a deliberate,
logged, availability-first exception — and is demonstrable live via the `auth-outage` demo.

## Top risks (from the threat model)

| Rank | What | Mitigation |
|------|------|-----------|
| 1 (TM-19) | Confused deputy: injection makes the agent misuse its **own valid** token | Scopes cap blast radius; auth does **not** stop the hijack — the headline lesson |
| 2 (TM-08) | Fail-open during a JWKS outage becomes an auth bypass | `fail_closed` default + last-known-good keys + circuit breaker |
| 3 (TM-10) | Algorithm confusion (`alg=none`, HS256/RS256) | Hardcoded RS256 allow-list, pinned by broken-token fixtures |
| 4 (TM-02/17) | Client-secret theft (incl. the agent's own shell reading its env) | The 300 s token isn't the crown jewel — the secret is; keep it off the tool workload |
| 5 (TM-11) | Audience confusion — a token minted for another service | `aud` checked against the canonical MCP URI (RFC 8707) |

## Cost and footprint

Two `python:3.11-slim` containers (128 Mi and 256 Mi), matching the existing stack; no JVM,
no external IdP. agentgateway is opt-in (`docker compose --profile gateway up`), so the
default laptop footprint grows by just those two services.

## The headline lesson

Authentication is necessary but not sufficient against prompt injection. A hijacked agent
holding a valid, correctly scoped token is still a confused deputy — within its scopes, its
tool calls succeed. The value of the token boundary is **blast-radius reduction** (scope the
agent to `tools:read` and the injected `execute_command` is denied), layered with the
segmentation, least-privilege, and egress controls the rest of the lab already teaches.
