# Threat Model — Authenticated MCP Server

**Feature:** OAuth client-credentials + JWKS-verified MCP server for DevBot's four tools
**Status:** Design-stage threat model (written before implementation; IDs are referenced by the implementation plan)
**Spec baseline:** MCP authorization spec 2025-06-18 (server as pure OAuth 2.1 resource server), RFC 8725 (JWT BCP), RFC 9728 (Protected Resource Metadata), RFC 8707 (resource indicators), OWASP "Fail Securely", OWASP Agentic Applications Top 10 (2026)

This lab already shows that prompt injection turns a helpful agent into an attacker.
The authenticated-MCP feature moves DevBot's four tools (`query_database`,
`fetch_webpage`, `execute_command`, `github_create_issue`) behind a network boundary
with real OAuth. This document asks the obvious next question: **what does
authentication actually buy you against an injected agent — and what new attack
surface does the auth machinery itself add?** Both answers are teaching material, so
every threat below maps to something the lab can demonstrate.

---

## 1. Scope & assumptions

### In scope

- **auth-server** — the purpose-built FastAPI token issuer: `POST /token`
  (client_credentials), `GET /.well-known/jwks.json`, discovery metadata, and the
  deliberately dangerous `/demo/mint-broken` fixture endpoints.
- **mcp-server** — FastMCP 2.x streamable-HTTP server hosting the four tools, with the
  hand-written JWT/JWKS `TokenVerifier` (the **primary enforcement point**) and the
  per-tool scope map.
- **agentgateway** (optional, `--profile gateway`) — secondary enforcement point;
  JWT authn + CEL tool-level RBAC in front of mcp-server.
- **devbot-agent as OAuth client** — `src/auth.py` client-credentials client, token
  cache, and the Bearer-authenticated MCP transport.
- **The interaction between the lab's existing prompt-injection vector and the new
  auth layer** — the poisoned wiki page is still the entry point; the question is what
  the token boundary changes.

### Out of scope

- The pre-existing threat surface of the lab itself (intentionally vulnerable shell/SQL
  tools, poisoned wiki) — covered by [`docs/ARCHITECTURE.md`](../../ARCHITECTURE.md)
  and [`SECURITY.md`](../../../SECURITY.md).
- Human-interactive OAuth flows (authorization code, PKCE, consent UIs). The lab is
  machine-to-machine only; confused-deputy variants that need a consent cookie are
  discussed as architecture notes, not runnable exploits.
- Production IdP hardening. `auth-server` is **explicitly not a production IdP**; it
  exists to make token issuance readable and to mint broken tokens on purpose.

### Assumptions

| # | Assumption | Consequence if violated |
|---|------------|-------------------------|
| A1 | The lab runs on a single trusted host; all ports bind `127.0.0.1` (per SECURITY.md). Traffic is plaintext HTTP inside the compose network. | On a shared network, every bearer token is sniffable (no TLS). This is a documented lab simplification — production requires TLS everywhere, and the threat model calls out where TLS is the real mitigation. |
| A2 | The Docker bridge network's service-name DNS is trustworthy (no attacker container doing DNS spoofing). | JWKS poisoning via DNS (TM-07) becomes trivial. The bundled `attacker-server` is a *sink*, not a network MITM, by design. |
| A3 | `.env` is never committed and holds only lab-grade secrets (`CHANGE_ME` placeholders in `.env.example`, gitleaks in CI). | Client-secret theft (TM-02) stops being theoretical. |
| A4 | The LLM (live mode) is untrusted-by-design: injected content *will* steer it. We do not assume model-level defenses. | n/a — this is the lab's premise. Auth is evaluated as an infrastructure control against an already-compromised planner. |
| A5 | Scripted mode makes no auth network calls; all denials there are `override_result` steps. | Scripted mode cannot be attacked through this surface; threats below apply to live mode and to anyone who deploys this pattern for real. |

---

## 2. System diagram and trust boundaries

```
                        TB1: agent process boundary
 ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐              TB3: issuer boundary
 │  DevBot Agent (OAuth client) │        ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐
 │  ┌──────────┐ ┌───────────┐ │ (1)    │  auth-server :8085        │
 │  │ LangGraph │ │ src/auth  │─┼────────┼─> POST /token            │
 │  │ planner   │ │ token     │ │  creds │   (client_credentials)   │
 │  │ (LLM —    │ │ cache     │<┼────────┼── RS256 JWT, kid, at+jwt │
 │  │ UNTRUSTED │ └───────────┘ │ (2)    │   GET /.well-known/      │
 │  │ in Act 2) │               │        │       jwks.json <────────┼──┐
 │  └──────────┘               │        │   /demo/mint-broken ⚠     │  │
 └ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘        └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘  │
        │ (3) MCP streamable HTTP                                      │ (4) JWKS
        │     Authorization: Bearer <JWT>                              │     fetch +
        ▼                 TB2: resource-server boundary                │     cache
 ┌ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┐    │
 │  [optional: agentgateway :3000 — JWT authn + CEL tool RBAC]    │    │
 │                      │                                         │    │
 │  mcp-server :9000/mcp (canonical URI = aud)                    │    │
 │  ┌─────────────────┐   ┌──────────────────────────────┐        │    │
 │  │ verifier.py      │   │ per-tool scope map            │       │    │
 │  │ alg/iss/aud/exp/ │──>│ tools:read  → query_database, │       │────┘
 │  │ nbf/typ/kid +    │   │               fetch_webpage   │       │
 │  │ JWKS cache +     │   │ tools:execute → execute_cmd   │       │
 │  │ FAIL-OPEN/CLOSED │   │ tools:write → github_issue    │       │
 │  └─────────────────┘   └──────────────┬───────────────┘        │
 └ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ┘
                                         │ (5) tool execution with the
                 TB4: upstream boundary  ▼     SERVER'S OWN creds (never
 ┌──────────────┐  ┌────────────┐  ┌───────────┐   the inbound token)
 │ PostgreSQL    │  │ Wiki (incl.│  │ GitHub API │
 │ customers PII │  │ POISONED   │  │ (opt-in)   │
 └──────────────┘  │ runbook) ⚠ │  └───────────┘
                   └────────────┘
```

**Token flow (numbers above):** (1) agent authenticates with client id/secret and
requests scopes + `resource=http://mcp-server:9000/mcp`; (2) issuer mints a 5-minute
RS256 `at+jwt` with `aud` bound to that URI; (3) every MCP request carries it as a
Bearer header — never in a URL; (4) the verifier validates it against cached JWKS keys;
(5) tools run with the server's own upstream credentials.

### Trust boundaries

| Boundary | Separates | What crosses it | Why it matters |
|----------|-----------|-----------------|----------------|
| **TB1** agent process | Untrusted planner (LLM + injected content) from the credentialed client code | Tool-call intents chosen by the LLM | The client secret and token cache live on the *trusted* side, but the LLM decides *when* and *with what arguments* the token gets used. This asymmetry is the confused-deputy seam (TM-17). |
| **TB2** resource server | Anything on the network from tool execution | Bearer-authenticated MCP requests | The verifier is the control. Everything before signature+claims validation is attacker-controlled input, including the JWT header (`alg`, `kid`). |
| **TB3** issuer | Token-minting capability from everyone else | Client credentials in; signed JWTs + public JWKS out | Whoever crosses TB3 with valid client creds *is* DevBot as far as mcp-server knows. The private key never leaves; `/demo/mint-broken` deliberately punches holes in this boundary for fixtures. |
| **TB4** upstream | Tool implementations from real data/APIs | SQL, HTTP, shell, GitHub calls using the server's own creds | The MCP token-passthrough prohibition lives here: the inbound JWT must never cross TB4 (TM-13). |

---

## 3. STRIDE threat catalog

Threats are grouped by component. Each entry: **ID · STRIDE class · attack path ·
mitigation (tied to the design) · residual risk.** Mitigations marked **[demo]** are
runnable lab demonstrations; **[fixture]** means a `/demo/mint-broken` negative-path
test drives it in pytest.

### 3.1 Token issuer (auth-server)

| ID | STRIDE | Threat |
|----|--------|--------|
| TM-01 | Spoofing | Issuer impersonation |
| TM-02 | Spoofing / Elevation | Client-secret theft → attacker mints real tokens |
| TM-03 | Elevation | `/demo/mint-broken` reachable outside the lab |
| TM-04 | Tampering | Scope-narrowing bypass at the token endpoint |
| TM-05 | DoS | Token-endpoint stampede / outage |

**TM-01 — Issuer impersonation.**
*Attack path:* a rogue service answers `http://auth-server:8085` (compose service-name
squatting, or a copy-paste of the lab with `OAUTH_ISSUER` pointed somewhere attacker-
controlled) and mints tokens signed with its own key.
*Mitigation:* the verifier pins `iss` by **exact, case-sensitive string match** and
fetches JWKS only from the configured `JWKS_URL` — never from `jku`/`x5u` token headers
(RFC 8725 §2.8). A wrong-`iss` token is a stock fixture. **[fixture]**
*Residual risk:* inside one compose network with plaintext HTTP (A1/A2), an attacker
who controls DNS controls both `iss` reality and JWKS. Accepted for the lab; the
production note is "TLS + certificate validation on the issuer URL is what makes `iss`
pinning meaningful."

**TM-02 — Client-secret theft.**
*Attack path:* `OAUTH_CLIENT_SECRET` leaks (committed `.env`, `docker inspect`, log
line, or the LLM echoing env vars via `execute_command` — note the agent's *own shell
tool* can read its own secrets, see TM-19). Attacker runs the client-credentials flow
and gets fully valid tokens with full scopes.
*Mitigation:* `.env.example` ships `CHANGE_ME`; gitleaks runs in CI and pre-commit
(repo convention, extended with the new secret names in `.gitleaks.toml`); tokens are
short-lived (300 s) so a stolen *token* ages out fast — but a stolen *secret* does not.
*Residual risk:* **High by construction.** Client-credentials with a shared secret is
the weakest confidential-client auth OAuth 2.1 allows; the spec prefers
`private_key_jwt`/mTLS (§2.4). The lab keeps the shared secret because it is readable,
and documents the upgrade path. This is a stated teaching trade-off, not an oversight.

**TM-03 — Broken-token fixture endpoints in the wrong environment.**
*Attack path:* someone deploys the lab beyond a laptop; `/demo/mint-broken?variant=...`
hands out `alg=none`, wrong-`aud`, expired, and HS256-confusion tokens to anyone who
asks, and `variant=hs256-confusion` in particular is a working forgery kit if any
*other* service in the environment validates sloppily.
*Mitigation:* every broken variant is rejected by the lab's own verifier (that is the
point); SECURITY.md's "never deploy outside an isolated environment" rule extends to
this service; the endpoint lives under `/demo/` and the threat model flags it in bold.
*Residual risk:* the endpoints are unauthenticated by design. A
`DEMO_FIXTURES_ENABLED=false` kill switch is cheap insurance and recommended for the
implementation (default `true` in compose, `false` in the k8s manifests).

**TM-04 — Scope-narrowing bypass.**
*Attack path:* client requests `scope=tools:read tools:execute tools:write` and the
issuer grants it blindly; or a bug makes the issuer echo *requested* rather than
*granted* scope.
*Mitigation:* issuer narrows scope per registered client and **returns the granted
scope in the token response** (OAuth 2.1 §4.2 requires this when narrowed); pytest
asserts that a client registered read-only cannot obtain `tools:execute` — since the
lab's single real client is registered with the full ceiling, the test must **patch
`client_scope_ceiling` to `"tools:read"`** and then assert a `tools:execute` request
yields neither that scope in the response nor in the token's `scope` claim. **[fixture]**
*Residual risk:* the lab has one real client; multi-client scope policy is ~10 lines of
dict and worth reading, but bugs there only matter in the one-demo-client world if
TM-02 already happened.

**TM-05 — Token-endpoint outage or stampede.**
*Attack path:* auth-server dies (the demo literally does `docker compose stop
auth-server`) or N concurrent tool calls each trigger a token fetch.
*Mitigation:* agent-side cache keyed by `(token_url, client_id, scope, resource)`,
proactive refresh at `exp−30s`, and a **single-flight lock** so concurrent calls make
one request; server-side JWKS caching means issued tokens keep verifying during the
outage. **[demo — this is step 1 of the fail-policy demo]**
*Residual risk:* once the last cached token expires during a long outage, the agent
cannot act at all. Correct and intended: that *is* fail-closed at the client.

### 3.2 JWKS endpoint and key handling

| ID | STRIDE | Threat |
|----|--------|--------|
| TM-06 | Tampering | `kid` header injection |
| TM-07 | Tampering / Spoofing | JWKS poisoning (substituting attacker keys) |
| TM-08 | DoS | JWKS outage — the fail-open/fail-closed decision point |
| TM-09 | Information disclosure | Key-rotation window confusion |

**TM-06 — `kid` injection.**
*Attack path:* the JWT header is attacker-controlled input *before* any signature
check. A hostile `kid` (`../../etc/passwd`, SQLi-shaped, 10 KB of junk) probes the key
lookup for path traversal, injection, or log poisoning (RFC 8725 §2.8 names this).
*Mitigation:* `kid` is sanitized (length-capped, charset-restricted) and used **only**
as a dictionary key into the parsed JWKS cache — never in a path, query, or shell;
unknown `kid` triggers at most **one rate-limited JWKS refetch** then fails. A
hostile-`kid` fixture asserts clean 401 with no side effects. **[fixture]**
*Residual risk:* negligible once lookup is a dict hit; the test exists to keep it one.

**TM-07 — JWKS poisoning.**
*Attack path:* attacker substitutes their own public key into what mcp-server trusts:
(a) MITM/DNS on the JWKS fetch (see A2), (b) a malicious `jku`/`x5u` header pointing at
an attacker URL, or (c) cache poisoning if the cache keyed on anything
attacker-influenced. With a poisoned key set, the attacker signs arbitrary tokens that
verify.
*Mitigation:* JWKS URL is **static config**, never derived from token headers
(`jku`/`x5u` are ignored entirely — RFC 8725 §2.9); the cache is keyed by `kid` from
the fetched document only; agentgateway in the optional profile does the same from its
own static config (defense in depth: *two* independently configured key sources).
*Residual risk:* plaintext HTTP inside compose means a true on-network MITM wins (A1).
Documented as the lab's loudest "TLS is not optional in production" callout.

**TM-08 — JWKS outage.**
*Attack path:* auth-server is down **and** mcp-server holds no usable cached key for
the token's `kid` (cold cache after restart, or key rotation during the outage). The
verifier cannot establish signature validity at all.
*Mitigation:* this is the **only** decision point `AUTH_FAILURE_MODE` governs — see
§4 for the full policy. Last-known-good keys served past TTL, a 3-failure circuit
breaker with 30 s half-open probes, and `Retry-After: 30` on 503 are the availability
mitigations that make fail-closed livable. **[demo — the centerpiece outage demo]**
*Residual risk:* under `fail_open`, an unverifiable token is accepted (with loud
audit logging and `X-Auth-Degraded: true`). That residual risk is the *lesson*, and
it is quantified in §4.

**TM-09 — Rotation-window confusion.**
*Attack path:* issuer rotates its keypair; tokens signed with the old key are still in
flight, or the server's cache still lacks the new key → spurious 401s, or worse,
operators "fix" it by widening leeway/disabling checks.
*Mitigation:* unknown-`kid` → single refetch (picks up new keys immediately); old keys
remain in the JWKS until their tokens age out (issuer keeps the previous key published
for ≥ token lifetime).
*Residual risk:* low; 300 s tokens make the window small. The demo's
`JWKS_CACHE_TTL=60` makes the mechanics visible on a human timescale.

### 3.3 Enforcement point (verifier.py — primary; agentgateway — secondary)

| ID | STRIDE | Threat |
|----|--------|--------|
| TM-10 | Spoofing / Elevation | Algorithm confusion (`alg=none`, HS256 key confusion) |
| TM-11 | Spoofing / Elevation | Audience confusion — a valid token for the *wrong* resource |
| TM-12 | Spoofing | Expired/not-yet-valid token replay; clock-skew abuse |
| TM-21 | Elevation | Gateway bypass (profile `gateway` only) |

**TM-10 — Algorithm confusion.** *(marquee fixture)*
*Attack path:* two classics from RFC 8725. (a) `alg=none` — a token that declares it
carries no signature, hoping the verifier honors the header. (b) HS256/RS256 key
confusion — a token whose header declares a MAC algorithm, hoping the verifier applies
its (public) RSA key material as if it were a shared secret, so public information
becomes signing capability (RFC 8725 §2.1, §3.1).
*Mitigation:* the verifier **hardcodes** the accepted-algorithm set to `{RS256}` and
passes it explicitly to PyJWT; the header's `alg` field is never trusted to choose the
algorithm, and each key is bound to exactly one algorithm. Both attacks are therefore
rejected *by construction*, before any key lookup. The `none` and `hs256-confusion`
`/demo/mint-broken` variants must each produce a clean 401. **[fixture]**
*Residual risk:* near zero while the allowlist stays hardcoded; the two fixtures exist
so a refactor that loosens it fails CI. agentgateway independently enforces its own
algorithm policy in the optional profile.

**TM-11 — Audience confusion.** *(marquee fixture)*
*Attack path:* a token with a perfectly valid signature from the real issuer — but
minted for a *different* resource — is replayed against mcp-server. Any service in a
shared-issuer world that skips the `aud` check will accept every other service's
tokens (the "access token privilege restriction" failure in the MCP authorization
spec).
*Mitigation:* the client sends `resource=http://mcp-server:9000/mcp` (RFC 8707); the
issuer stamps that canonical URI into `aud`; the verifier **requires** its own
canonical URI in `aud`, rejecting otherwise-valid tokens. The `wrong-aud` fixture
drives the negative test. **[fixture]**
*Residual risk:* audience binding is string matching, so the canonical URI must be
written once and imported everywhere (compose env, issuer config, verifier config).
When the gateway profile is active, `aud` remains the mcp-server canonical URI — the
gateway validates the same claim, so repointing the client does not change the token.

**TM-12 — Expired / not-yet-valid token replay.**
*Attack path:* a captured token is replayed after expiry, or a token with a future
`nbf` is presented early; sloppy leeway handling stretches the usable window.
*Mitigation:* `exp` and `nbf` validated with a bounded **30 s leeway**; tokens live
300 s; expiry math needs no IdP, so an expired token is **401 in both failure modes**
(§4, row c). The `expired` fixture plus a boundary test at leeway ± 1 s pin the
behavior. `jti` is logged on every acceptance for after-the-fact correlation.
**[fixture]**
*Residual risk:* within its 300 s + 30 s window, a stolen token *is* the client — there
is no revocation/denylist in the lab (a `jti` denylist is noted as the production
extension). Short lifetime is the real control; see TM-17 for theft paths.

**TM-21 — Gateway bypass (profile `gateway` only).**
*Attack path:* with agentgateway fronting mcp-server, a client that talks to
`mcp-server:9000` directly skips the gateway's CEL tool-RBAC and `tools/list`
filtering.
*Mitigation:* by design, mcp-server **never delegates** verification — its own
`verifier.py` runs identically whether or not the gateway is in front, so a bypass
still faces full authn + scope checks. The gateway adds policy, it is not the only
policy.
*Residual risk:* gateway-*only* features (tool-list filtering, gateway-served RFC 9728
metadata) are bypassable in the flat lab network. Documented as the defense-in-depth
lesson: in production the backend would be network-isolated so only the gateway can
reach it.

### 3.4 MCP server (resource server behavior)

| ID | STRIDE | Threat |
|----|--------|--------|
| TM-13 | Information disclosure / Elevation | Token passthrough to upstream APIs |
| TM-14 | Elevation | Scope escalation at tool dispatch |
| TM-15 | Spoofing | Session hijacking on streamable HTTP |
| TM-16 | Information disclosure / Repudiation | Tokens or claims leaking into logs and errors |

**TM-13 — Token passthrough anti-pattern.** *(explicitly forbidden by the MCP spec)*
*Attack path:* the MCP server forwards the inbound Bearer token to an upstream (GitHub
API, database proxy). Upstream now trusts a token minted for someone else, rate
limiting and audit trails attribute the wrong principal, and the MCP server becomes a
generic authenticated proxy for whatever its token can reach.
*Mitigation:* mcp-server uses **its own** upstream credentials (`DATABASE_URL`,
optional `GITHUB_PAT` from its own env) for every tool execution; the inbound JWT is
consumed at the verifier and never placed on an outbound request. A test asserts no
outbound call carries the inbound `Authorization` header. The spec language — "MCP
servers MUST NOT accept or transit any other tokens" — is quoted beside the code.
*Residual risk:* low with the test in place. The design deliberately *discusses* a
hypothetical "passthrough mode" in docs only, as the anti-pattern contrast, without
implementing it.

**TM-14 — Scope escalation at dispatch.**
*Attack path:* a token carrying only `tools:read` invokes `execute_command`; or a new
tool is added without a scope-map entry and dispatch falls through to "allowed."
*Mitigation:* per-tool scope map checked at dispatch (`tools:read` →
`query_database`/`fetch_webpage`; `tools:execute` → `execute_command`; `tools:write` →
`github_create_issue`), with **default-deny for any tool not in the map**. Failure is
`403` + `error="insufficient_scope"` naming the required scope in `WWW-Authenticate` —
the scope-elevation teaching moment, scripted into Act 3. **[demo]**
*Residual risk:* scope checks live in one dispatch chokepoint; a tool invoked through
any other path would skip them. The implementation keeps a single `_execute_tool`-style
dispatcher to preserve the chokepoint, and a test enumerates registered tools against
the map.

**TM-15 — Session hijacking.**
*Attack path:* streamable HTTP uses session IDs for transport continuity. If the
server treats "has a session ID" as "is authenticated," a guessed or leaked session ID
becomes a credential (MCP security best practices: sessions **MUST NOT** be used for
authentication).
*Mitigation:* FastMCP session IDs are non-deterministic, and the verifier runs on
**every request** — a valid session with a missing/expired token still gets 401.
*Residual risk:* low; the per-request-verification property is asserted by a test that
reuses a session after letting its token expire.

**TM-16 — Tokens and claims in logs; chatty errors.**
*Attack path:* a debug log prints the raw Bearer header, or 401 bodies leak verifier
internals; anyone with log access harvests live tokens (and the lab *displays* logs in
the demo panel).
*Mitigation:* log `sub`, `jti`, `kid`, and the failure reason — never the raw token;
error responses carry only RFC 6750 error codes (`invalid_token`,
`insufficient_scope`) plus the `WWW-Authenticate` challenge. The repudiation flip
side: every degraded acceptance under fail-open logs a structured
`auth_degraded_accept` event with `sub` and `jti` (§4), so accept-without-proof is
never silent.
*Residual risk:* the demo intentionally surfaces auth decisions in UI logs; keeping
tokens out of them is a review-time rule plus a grep-shaped test over captured log
output.

### 3.5 Agent as OAuth client (devbot-agent)

| ID | STRIDE | Threat |
|----|--------|--------|
| TM-17 | Information disclosure | Token / secret theft on the client side |
| TM-18 | Spoofing / SSRF | Malicious discovery metadata or repointed MCP URL |

**TM-17 — Token and secret theft, client side.**
*Attack path:* the access token or client secret is exposed via URLs, logs, error
traces, or environment access. Specific to this lab: in scripted/in-process mode the
shell tool runs **in the agent container**, so an injected `execute_command("env")`
can read `OAUTH_CLIENT_SECRET` — the agent can be steered into stealing its own
credentials. In live MCP mode the shell executes in the mcp-server container, which
holds no client secret (but does hold the server's upstream creds — a different prize).
*Mitigation:* tokens travel **only** in the `Authorization` header, never in query
strings (OAuth 2.1 bearer rules); the token cache is in-memory only; 300 s lifetime
bounds exposure; secrets enter via env with `CHANGE_ME` placeholders and gitleaks
enforcement. The container-boundary nuance above is called out in DEMO.md as a
teachable moment rather than silently fixed.
*Residual risk:* **the env-var exposure to the agent's own shell tool is real and
intentional** — it is this lab's version of "an agent with a shell owns its own
process." Production guidance: don't co-locate credentials with a shell-capable agent;
use short-lived injected credentials or a token broker.

**TM-18 — Malicious discovery metadata / repointed server.**
*Attack path:* the client resolves where to send credentials and tokens from
configuration and discovery documents. If `MCP_SERVER_URL` or the RFC 9728 metadata is
attacker-influenced, the agent can be induced to present its token to (or fetch
authorization-server metadata from) a hostile endpoint — the SSRF-via-discovery class
from the MCP client guidance.
*Mitigation:* the lab client uses **static configuration** for the token URL and MCP
URL (pydantic-settings, operator-controlled env), and sends the Bearer header only to
`mcp_server_url`. Discovery metadata is served and demonstrated but is not the
client's source of truth.
*Residual risk:* config is trusted; whoever sets env vars owns the client. Standard,
and out of scope beyond A3.

### 3.6 Prompt injection meets the auth layer

This is the section the rest of the lab exists for. The poisoned wiki page still
arrives through `fetch_webpage`; the planner is still steerable (A4). What changes?

| ID | STRIDE | Threat |
|----|--------|--------|
| TM-19 | Elevation (confused deputy) | Injected content makes the agent misuse its **own valid token** |
| TM-20 | Elevation | Injection-driven scope elevation |

**TM-19 — Confused deputy via prompt injection.** *(the headline threat)*
*Attack path:* authentication proves *who is calling* — it says nothing about *why*.
The injected runbook steers the agent, the agent dutifully attaches its perfectly
valid token, and `query_database` / `execute_command` run with full authorization.
Every signature, `iss`, `aud`, `exp`, and scope check passes, because the deputy is
real; only its intent is attacker-supplied. This is the classic confused deputy with
an LLM as the deputy (OWASP Agentic Top 10: agent tool misuse).
*Mitigation (partial, honestly labeled):* auth **cannot** stop this attack — the lab
demonstrates exactly that in Act 2 with auth enforced and the kill chain still
running. (Canonical act mapping, shared with the implementation plan, Tasks 2.6/4.2:
**Act 1** = `AUTH_MODE=off`, the control-off baseline; **Act 2** = auth enforced with
the full scope ceiling — every check passes, the kill chain still runs; **Act 3** =
auth enforced with scope narrowed to `tools:read` — the same injected calls die with
403/401.) What the token layer *does* buy: (1) **scope-bounded blast radius** — a
deployment that grants DevBot only `tools:read` makes the injected
`execute_command` die with 403 regardless of what the model wants (demonstrated as
the Act 3 `insufficient_scope` beat); (2) **attributable audit** — every tool call
is tied to `sub`/`jti`, so the kill chain is reconstructable; (3) **revocable
access** — rotating the client secret cuts the agent off in ≤ 300 s. The *existing*
controls (egress allow-lists, segmentation, treating fetched content as untrusted)
remain the primary defense, exactly as in the current lab.
*Residual risk:* **high, and the point.** Within granted scopes, an injected agent is
indistinguishable from a well-behaved one at the auth layer. The threat model's
one-line summary for executives: *authentication narrows what a hijacked agent can
reach; it does not stop the hijack.*

**TM-20 — Injection-driven scope elevation.**
*Attack path:* injected content tells the agent to go get more power: re-request a
token with broader scope, call the token endpoint directly via `fetch_webpage` or
`execute_command` (curl), or respond to a 403 scope challenge by asking for the
missing scope.
*Mitigation:* the requested scope is **static configuration** (`oauth_scope` in
pydantic-settings), not an LLM-controllable parameter — the token client is not
exposed to the planner as a tool; the issuer narrows scope per registered client
(TM-04), so even a hand-crafted token request from inside the agent container cannot
exceed the client's registration; scope elevation is deliberately *not* automated on
403 — the challenge names the missing scope for a human, not for the agent.
*Residual risk:* an injected agent that can run shell **in a container holding the
client secret** can perform the whole client-credentials flow itself (TM-17 chain) up
to the registered scope ceiling. The ceiling holds; everything below it does not. The
Act 2/Act 3 contrast makes this chain visible instead of hiding it.

Related, lower-severity: **tool poisoning** via MCP tool descriptions (a hostile
server advertising manipulative tool metadata) applies when an agent consumes
*third-party* MCP servers. Here the server is in-repo and reviewed; the threat is
documented as the supply-chain variant (OWASP agentic supply chain) with the existing
injection harness as the natural place to demo it later.

---

## 4. Fail-open vs fail-closed

### The policy

`AUTH_FAILURE_MODE = fail_closed | fail_open` (default **fail_closed**), read by
pydantic-settings and consulted at **exactly one decision point** in `verifier.py`:

> The token's key cannot be resolved — the JWKS cache holds no usable key for this
> `kid` **and** a live JWKS fetch has just failed.

Everything else is unconditionally closed, in both modes:

| Situation | fail_closed | fail_open |
|-----------|------------|-----------|
| Signature invalid, wrong `iss`/`aud`, bad `alg`/`typ` | 401 | **401** (the toggle never excuses an *invalid* token, only an *unverifiable* one) |
| Expired / future `nbf` (clock math needs no IdP) | 401 | **401** |
| JWKS refresh fails, **warm cache** | Not a policy event: last-known-good keys served past TTL; requests keep succeeding; background retry every 15 s | same |
| IdP outage + unknown `kid` / cold cache | **503** + `Retry-After: 30`, structured `auth_unavailable` log | Token accepted **iff** every non-signature check passes (`iss`/`aud`/`exp`/`nbf`/`typ`); loud `auth_degraded_accept` audit log with `sub`/`jti`; response header `X-Auth-Degraded: true` |

A circuit breaker wraps the JWKS fetch (open after 3 consecutive failures, half-open
probe at 30 s) and exposes its state on `/health` for the demo panel.

### Rationale

OWASP "Fail Securely": a security control's failure must follow the deny path —
fail-open-by-accident (an exception handler that forgets to deny) is a vulnerability
class, which is why the lab implements the choice as one explicit, visible,
default-closed branch rather than as exception-handling behavior. Industry practice is
fail-closed with aggressive JWKS caching + last-known-good keys + circuit breakers as
the availability mitigation; fail-open exists only as a deliberate, bounded, logged
exception for availability-critical paths. agentgateway, notably, ships **only**
fail-closed with cached keys and offers no fail-open knob — the production contrast to
this deliberately configurable lab setting, and one reason it is not the primary
enforcement point here.

### What each setting trades

| Setting | Accepts this risk | To defeat this threat |
|---------|-------------------|----------------------|
| **fail_closed** | **Availability loss as a weapon (DoS amplification):** an attacker who can take down or unreach the issuer (TM-05/TM-08) — or merely outlast the key cache across a server restart — converts an IdP outage into a full agent outage (503s). | Accepting unverifiable tokens. Nothing unsigned-and-unproven ever executes a tool. |
| **fail_open** | **Forgery during outages:** an attacker who can *both* induce JWKS unavailability *and* present a well-formed token (plausible `iss`/`aud`/`exp`, unverifiable signature) executes tools. The DoS becomes an authn bypass — the attacker is incentivized to *cause* the outage. | Outage-coupled downtime. The agent keeps working through IdP failures, with every degraded acceptance audited. |

The honest framing the demo delivers: **fail_closed turns an auth outage into an
availability incident; fail_open turns it into a potential security incident.** The
warm-cache row is the most important one — with last-known-good keys, most outages are
*neither*, which is why the demo shows that first (stop auth-server → tool calls keep
succeeding), before the cold-cache contrast (restart mcp-server → 503 vs
degraded-accept side by side), and finally recovery (breaker half-opens, normal
401/403 semantics resume). In scripted mode the same contrast is told as
`override_result` steps, so the lesson works offline.

---

## 5. Top risks at a glance

| Rank | ID | One line |
|------|----|----------|
| 1 | TM-19 | Confused deputy: injection makes the agent abuse its own valid token — auth narrows blast radius, it does not stop the hijack. |
| 2 | TM-08/§4 | Fail-open under JWKS outage converts a DoS on the issuer into an authentication bypass; default is fail_closed. |
| 3 | TM-10 | Algorithm confusion (`none`, HS256-vs-RS256) — defeated by a hardcoded RS256 allowlist, pinned by fixtures. |
| 4 | TM-02/TM-17 | Client-secret theft — including by the agent's own shell tool reading its env; the secret, not the token, is the crown jewel. |
| 5 | TM-11 | Audience confusion — a valid token for another service, rejected only because `aud` is checked against the canonical MCP URI. |
| 6 | TM-13 | Token passthrough upstream — explicitly forbidden; upstream calls use the server's own credentials, verified by test. |
| 7 | TM-14 | Scope escalation at dispatch — default-deny scope map; `tools:read` cannot run `execute_command`. |

## 6. References

- MCP Authorization, 2025-06-18 — <https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization>
- MCP Security Best Practices — <https://modelcontextprotocol.io/specification/2025-06-18/basic/security_best_practices> (served the current revision; cited requirements present from 2025-06-18)
- MCP Authorization, 2025-03-26 (legacy AS-co-hosting model, historical contrast) — <https://modelcontextprotocol.io/specification/2025-03-26/basic/authorization>
- RFC 8725 — JSON Web Token Best Current Practices
- RFC 9728 — OAuth 2.0 Protected Resource Metadata
- RFC 8707 — Resource Indicators for OAuth 2.0
- RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens (`at+jwt`)
- OAuth 2.1 — draft-ietf-oauth-v2-1-13
- OWASP "Fail Securely" — <https://community.owasp.org/Fail_securely>
- OWASP JWT Cheat Sheet — <https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_Cheat_Sheet.html>
- OWASP Agentic Applications Top 10 (2026) — <https://genai.owasp.org>

*Companion documents: the phased implementation plan (`IMPLEMENTATION_PLAN.md`) in
`docs/plans/authenticated-mcp/`, the executive summary (`EXECUTIVE_SUMMARY.md`,
forthcoming — created by the plan's Task 7.2), plus the lab's existing
[`ARCHITECTURE.md`](../../ARCHITECTURE.md) control mapping, which Act 3's auth beats
extend.*