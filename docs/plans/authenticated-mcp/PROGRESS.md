# Authenticated MCP — Implementation Progress

Ledger for the loop executing [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md).
One checkbox per task; the first unchecked task is always the next target.
A task is ticked only after its verify command(s) and the affected pytest
suites pass, with scripted offline mode green.

## Phase 1 — auth-server service (token issuer)

- [x] Task 1.1 — Scaffold the service
- [ ] Task 1.2 — Config and key material
- [ ] Task 1.3 — Token endpoint, JWKS, discovery, health
- [ ] Task 1.4 — Broken-token fixture endpoints (TM-03, TM-10, TM-11, TM-12)
- [ ] Task 1.5 — Tests
- [ ] Task 1.6 — Compose + CI + env wiring

## Phase 2 — mcp-server service (resource server + verifier)

- [ ] Task 2.1 — Scaffold
- [ ] Task 2.2 — Config
- [ ] Task 2.3 — Tools module (extraction, not move)
- [ ] Task 2.4 — The hand-written verifier (primary enforcement point)
- [ ] Task 2.5 — Scope map and dispatch (TM-14)
- [ ] Task 2.6 — FastMCP server + RFC 9728 metadata
- [ ] Task 2.7 — Negative-path tests (threat-model-driven)
- [ ] Task 2.8 — Compose + CI

## Phase 3 — Agent client integration (behind `mcp_enabled`, default off)

- [ ] Task 3.1 — Settings
- [ ] Task 3.2 — The OAuth client-credentials client
- [ ] Task 3.3 — Wire MCP transport into the live agent
- [ ] Task 3.4 — Env / compose / secrets wiring
- [ ] Task 3.5 — Regression gate

## Phase 4 — Demo narrative wiring (scripted + live outage)

- [ ] Task 4.1 — Scripted auth-denial beats
- [ ] Task 4.2 — Act state machine ties auth on/off
- [ ] Task 4.3 — Live fail-policy outage demo

## Phase 5 — Optional agentgateway profile (defense-in-depth contrast)

- [ ] Task 5.0 — Verify the image pin and config surface (do this first)
- [ ] Task 5.1 — Gateway config
- [ ] Task 5.2 — Compose profile
- [ ] Task 5.3 — Docs for repointing

## Phase 6 — Deployment parity (k8s + Helm)

- [ ] Task 6.1 — k8s manifests
- [ ] Task 6.2 — Helm parity

## Phase 7 — Threat model cross-links, docs, executive summary

- [ ] Task 7.1 — Extend standing docs
- [ ] Task 7.2 — Executive summary

## Phase 8 — Verification pass

- [ ] Task 8.1 — Full CI green
- [ ] Task 8.2 — End-to-end smoke (live)
- [ ] Task 8.3 — Scripted offline run (no auth containers)
- [ ] Task 8.4 — Secret hygiene final check

## Blockers

(none)
