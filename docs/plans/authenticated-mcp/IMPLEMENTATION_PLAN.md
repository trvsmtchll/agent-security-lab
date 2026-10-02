# Implementation Plan — Authenticated MCP Server

**Feature:** OAuth client-credentials + JWKS-verified MCP server for DevBot's four tools,
with a fail-open/fail-closed policy toggle and an optional agentgateway profile.
**Companion documents:** [`THREAT_MODEL.md`](./THREAT_MODEL.md) (TM-xx IDs referenced
throughout; every mitigation it promises appears below as a task) and the executive
summary `EXECUTIVE_SUMMARY.md` (**forthcoming** — it does not exist yet; it is created
in this directory by Task 7.2, or earlier by the planning workflow).
**Audience:** Claude agents executing this plan with no other context. Every file path
is real and relative to the repo root unless marked **(new)**.

---

## 1. Goal

Move DevBot's four in-process tools (`query_database`, `fetch_webpage`,
`execute_command`, `github_create_issue` — today plain Python functions in
`services/devbot-agent/src/tools.py`) behind a real network boundary:

1. A **FastMCP 2.x MCP server** (`services/mcp-server`, streamable HTTP) exposing the
   four tools behind a **hand-written ~80-line JWT/JWKS TokenVerifier** — the primary
   enforcement point, built to be read.
2. A **purpose-built FastAPI OAuth issuer** (`services/auth-server`, ~100 lines):
   `POST /token` (client_credentials) + JWKS + discovery, plus `/demo/mint-broken`
   endpoints that mint deliberately invalid tokens as RFC 8725 negative-path fixtures.
3. A **client-credentials OAuth client** in devbot-agent (`src/auth.py`) feeding a
   Bearer header into a `MultiServerMCPClient`, gated by `settings.mcp_enabled`
   (default `false`).
4. An **`AUTH_FAILURE_MODE` toggle** (`fail_closed` default | `fail_open`) consulted at
   exactly one decision point: JWKS unavailable AND no usable cached key.
5. An **optional agentgateway container** (pin confirmed at implementation time —
   Task 5.0) under `docker compose --profile gateway` as the production-pattern
   contrast (secondary enforcement, CEL tool RBAC).
6. Demo-narrative wiring (scripted 401/403 beats in Act 3, a live outage demo), k8s/Helm
   parity, threat-model-driven tests, and doc updates.

**Two invariants that must survive every phase:**

- **Scripted/offline mode keeps working with zero auth containers running.** The
  devbot-agent keeps its in-process tool copies; `mcp_enabled` defaults to `false`;
  all scripted auth denials are `override_result` steps. The existing ~1150 lines of
  pytest (which patch `src.agent.settings`) must pass untouched except where a phase
  explicitly says otherwise.
- **All host ports bind `127.0.0.1` only** (SECURITY.md invariant).

## 2. Chosen stack and versions

| Component | Choice | Version / pin |
|---|---|---|
| MCP server | FastMCP (Apache-2.0), streamable HTTP | `fastmcp>=2.11,<3.0` — pin the exact latest 2.x at implementation time |
| JWT verification | PyJWT + `PyJWKClient` | `PyJWT[crypto]==2.10.1` |
| Key generation | `cryptography` (transitive via PyJWT[crypto]; pin explicitly) | `cryptography>=44,<46` |
| OAuth issuer | FastAPI + uvicorn (repo's existing pattern) | `fastapi==0.115.6`, `uvicorn[standard]==0.34.0` (match `services/devbot-agent/requirements.txt`) |
| Agent MCP client | `langchain-mcp-adapters` (`MultiServerMCPClient`) | pin the newest version whose deps resolve against the repo's existing `langchain==0.3.14` / `langgraph==0.2.60` pins (the 0.1.x line). Note: upstream has merged this package into `langchain[mcp]` in langchain 1.x; do **not** upgrade langchain for this feature — record the migration note in a comment in `requirements.txt`. |
| Gateway (optional) | agentgateway standalone container | `cr.agentgateway.dev/agentgateway:v1.5.0` (Apache-2.0) — **confirm at implementation time** (like the fastmcp and langchain-mcp-adapters pins): this registry path, tag scheme, and version cannot be verified from this repo (upstream has historically published `ghcr.io` images with `0.x` tags). Verify per Task 5.0 before writing any gateway config. |
| Base images | `python:3.11-slim` (matches every existing Python service) | — |
| Tests | pytest, unittest.mock, no conftest/fixtures (repo convention) | `pytest==8.3.4` |

Canonical identifiers used everywhere (write once, import/configure everywhere — TM-11):

- **Issuer (`iss`):** `http://auth-server:8085`
- **Canonical MCP resource URI (`aud`):** `http://mcp-server:9000/mcp`
- **Scopes:** `tools:read` (query_database, fetch_webpage), `tools:execute`
  (execute_command), `tools:write` (github_create_issue)
- **Token:** RS256, header `{alg, kid, typ: "at+jwt"}`, lifetime 300 s, leeway 30 s

## 3. Non-goals

- No production IdP (Keycloak/Hydra/Dex rejected — see threat model §1 and the design
  record). `auth-server` is explicitly a readable toy issuer.
- No TLS inside the compose network (lab assumption A1; documented, not fixed).
- No human-interactive OAuth flows (authorization code, PKCE, consent).
- No token revocation/`jti` denylist (noted in docs as the production extension).
- No change to the agent's `:8000` API surface, nginx proxies, or the UIs.
- No removal of the in-process tool path — scripted mode depends on it.
- agentgateway is never the primary enforcement point and never a default service.
- No Kubernetes Gateway API / kgateway deployment (appendix note only).

## 4. Read these files first

| File | Why |
|---|---|
| `docs/plans/authenticated-mcp/THREAT_MODEL.md` | TM-xx IDs this plan implements; §4 defines the fail policy exactly |
| `services/devbot-agent/src/tools.py` | The four tool functions to copy into mcp-server |
| `services/devbot-agent/src/agent.py` | `_get_langchain_tools` (line ~36), `create_agent` (~94), `_TOOL_NAME_MAP` (~136), `_execute_tool` (~554) — the integration points |
| `services/devbot-agent/src/config.py` | pydantic-settings pattern to extend |
| `services/devbot-agent/src/scripted.py` | `_ACT3_FLOW` step shape (`blocked`, `override_result`, `auto_advance`) for the new auth beats |
| `services/devbot-agent/src/main.py` | `POST /set-act` + WebSocket `set_act` — the act state machine the auth demo hangs off |
| `services/devbot-agent/tests/test_agent.py` | Test style: `@patch("src.agent.settings")`, class-grouped, no fixtures |
| `docker-compose.yml` | Service style: 127.0.0.1 ports, healthcheck/depends_on pattern |
| `.env.example`, `.gitleaks.toml`, `scripts/pre-commit` | Placeholder + allowlist conventions for new secrets |
| `.github/workflows/ci.yml` | Per-service pytest steps + gitleaks job to extend |
| `k8s/devbot-agent.yaml`, `k8s/secrets.yaml`, `k8s/configmap.yaml`, `helm/agent-security-lab/values.yaml` | Deployment parity patterns |
| `SECURITY.md`, `docs/ARCHITECTURE.md`, `docs/DEMO.md` | Invariants and the three-act narrative to extend |

**Repo conventions (apply to all new Python):** Python 3.12 in CI on `python:3.11-slim`
images; PEP8 + type hints; pydantic v2; Google-style docstrings; `# Reason:` comments
for non-obvious logic; files under 500 lines; tests in `tests/` using
`unittest.mock.patch` with **no conftest.py and no pytest fixtures**;
`requirements-dev.txt` = `-r requirements.txt` + `pytest==8.3.4`.

---

## Phase 1 — auth-server service (token issuer)

### Task 1.1 — Scaffold the service

**Create (new):**

- `services/auth-server/Dockerfile` — copy the pattern of
  `services/devbot-agent/Dockerfile` minus nmap:

  ```dockerfile
  FROM python:3.11-slim
  WORKDIR /app
  COPY requirements.txt .
  RUN pip install --no-cache-dir -r requirements.txt
  COPY src/ ./src/
  EXPOSE 8085
  CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8085"]
  ```

- `services/auth-server/requirements.txt`:

  ```
  fastapi==0.115.6
  uvicorn[standard]==0.34.0
  PyJWT[crypto]==2.10.1
  pydantic==2.10.4
  pydantic-settings==2.7.1
  ```

- `services/auth-server/requirements-dev.txt`:

  ```
  # Test-only dependencies. Runtime deps live in requirements.txt.
  -r requirements.txt
  pytest==8.3.4
  httpx==0.28.1
  ```

  (httpx is dev-only: `fastapi.testclient` requires it.)

- `services/auth-server/src/__init__.py` (empty)
- `services/auth-server/tests/__init__.py` (empty)

**Acceptance:** `docker build services/auth-server` succeeds once src/main.py exists
(Task 1.2–1.4).

### Task 1.2 — Config and key material

**Create (new):** `services/auth-server/src/config.py` — same shape as
`services/devbot-agent/src/config.py`:

```python
"""Auth-server configuration using pydantic settings."""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Issuer settings loaded from environment variables."""

    # Canonical identifiers (TM-11: written once, used everywhere)
    issuer: str = "http://auth-server:8085"
    mcp_resource_uri: str = "http://mcp-server:9000/mcp"

    # Registered client (lab has exactly one real client)
    oauth_client_id: str = "devbot-agent"
    oauth_client_secret: str = "CHANGE_ME"
    # Scope ceiling for the registered client (TM-04: issuer narrows to this)
    client_scope_ceiling: str = "tools:read tools:execute tools:write"

    token_ttl_seconds: int = 300

    # TM-03: kill switch for the broken-token fixture endpoints.
    # Default true in compose (it is the lab), false in k8s manifests.
    demo_fixtures_enabled: bool = True

    auth_host: str = "0.0.0.0"
    auth_port: int = 8085

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

**Create (new):** `services/auth-server/src/keys.py` (~40 lines):

- `generate_keypair() -> KeyPair`: RSA-2048 via `cryptography`, generated **at process
  startup, in memory only — never written to disk, never committed** (keeps gitleaks'
  private-key rule quiet and TB3 intact). `kid` = first 16 hex chars of the SHA-256 of
  the public key DER.
- `KeyPair` dataclass/pydantic model: `kid`, `private_pem`, `public_jwk` (dict with
  `kty`, `n`, `e`, `alg: "RS256"`, `use: "sig"`, `kid`).
- Module keeps a list of current + previous keypairs; `rotate()` appends a new current
  key and **keeps the previous key published for >= token_ttl_seconds** (TM-09).
- Also generate one **HS256-style secret and a second "foreign" RSA keypair** at
  startup for the mint-broken fixtures (Task 1.4).

**Acceptance:** importable, unit-tested in Task 1.5.

### Task 1.3 — Token endpoint, JWKS, discovery, health

**Create (new):** `services/auth-server/src/main.py` (~100 lines core). Endpoints:

1. `POST /token` — `application/x-www-form-urlencoded`, per OAuth 2.1
   client-credentials:
   - Client auth via **both** `client_secret_basic` (Authorization: Basic) and
     `client_secret_post` (form fields); constant-time secret compare
     (`secrets.compare_digest`).
   - Validate `grant_type=client_credentials` else `400 {"error":
     "unsupported_grant_type"}`; bad creds → `401 {"error": "invalid_client"}` with
     `WWW-Authenticate: Basic`.
   - **Scope narrowing (TM-04):** granted = requested ∩ `client_scope_ceiling`
     (full ceiling when no scope requested). The **granted** scope is echoed in the
     response `scope` field — never the requested string.
   - `resource` parameter (RFC 8707) → becomes `aud`; default
     `settings.mcp_resource_uri`.
   - Mint RS256 JWT: header `{"alg": "RS256", "kid": <current>, "typ": "at+jwt"}`,
     claims `{"iss": settings.issuer, "sub": client_id, "aud": resource,
     "exp": now+300, "iat": now, "nbf": now, "jti": uuid4().hex, "scope": granted}`.
   - Response: `{"access_token": ..., "token_type": "Bearer", "expires_in": 300,
     "scope": granted}`.
2. `GET /.well-known/jwks.json` — `{"keys": [current.public_jwk, previous...]}`.
3. `GET /.well-known/oauth-authorization-server` — RFC 8414 metadata: `issuer`,
   `token_endpoint`, `jwks_uri`, `grant_types_supported:
   ["client_credentials"]`, `token_endpoint_auth_methods_supported:
   ["client_secret_basic", "client_secret_post"]`, `scopes_supported`.
4. `GET /health` — `{"status": "ok", "kid": <current kid>, "fixtures_enabled": bool}`.

**Acceptance criteria:**

- A `curl -u devbot-agent:CHANGE_ME -d 'grant_type=client_credentials&scope=tools:read'
  http://127.0.0.1:8084/token` returns a decodable RS256 `at+jwt` whose `scope` is
  `tools:read` and `aud` is the canonical MCP URI.
- A client requesting a scope outside the ceiling gets only the intersection back.
- No endpoint ever returns the private key; `/token` never logs the secret.

### Task 1.4 — Broken-token fixture endpoints (TM-03, TM-10, TM-11, TM-12)

**Modify:** `services/auth-server/src/main.py` — add
`GET /demo/mint-broken?variant=<v>` guarded by `settings.demo_fixtures_enabled`
(404 when disabled). Variants, each returning `{"access_token": ..., "variant": ...,
"why_broken": "<one-line lesson>"}` with otherwise-plausible claims:

| variant | Construction |
|---|---|
| `none` | header `{"alg": "none"}`, no signature (RFC 8725 §2.1) |
| `hs256-confusion` | header `{"alg": "HS256", "kid": <real kid>}` signed with the **public** key PEM bytes as the HMAC secret (key-confusion forgery) |
| `wrong-aud` | valid RS256 signature, `aud: "http://some-other-service/api"` |
| `wrong-iss` | signed with the **foreign** keypair, `iss: "http://evil-issuer:8085"` |
| `expired` | valid signature, `exp` = now − 3600, `iat`/`nbf` = now − 3900 |
| `hostile-kid` | valid signature with current key, but header `kid` = `"../../etc/passwd" + "A"*10240` (TM-06 probe) |

Unknown variant → `400` listing valid variants.

**Acceptance:** each variant decodes (with `verify_signature=False`) to the described
shape; `DEMO_FIXTURES_ENABLED=false` makes `/demo/mint-broken` return 404.

### Task 1.5 — Tests

**Create (new):** `services/auth-server/tests/test_token.py`,
`services/auth-server/tests/test_fixtures.py` — repo style (`fastapi.testclient`,
class-grouped, `@patch("src.main.settings")` / `@patch("src.config.settings")` where
env control is needed, no fixtures/conftest). Cover at least:

- happy path basic + post auth; `invalid_client` on wrong secret; `unsupported_grant_type`
- scope narrowing: requesting `tools:execute tools:admin` returns only the
  intersection with the ceiling (the unknown `tools:admin` is dropped); response
  `scope` == granted (TM-04)
- **TM-04 read-only client:** `@patch` `client_scope_ceiling` to `"tools:read"`
  (the registered default ceiling includes all three scopes, so this case exists
  only under the patch), request `scope=tools:execute`, and assert `tools:execute`
  appears in neither the response `scope` nor the minted token's `scope` claim
- token claims: `iss`/`aud`/`exp−iat==300`/`jti` present; header `typ == "at+jwt"`,
  `kid` matches JWKS
- JWKS: current `kid` present; after `rotate()`, previous key still published (TM-09)
- every mint-broken variant's defining defect; fixtures 404 when disabled (TM-03)

**Verify command:**

```bash
cd services/auth-server && pip install -r requirements-dev.txt && python -m pytest tests/ -v
```

### Task 1.6 — Compose + CI + env wiring

**Modify `docker-compose.yml`** — add (keep existing style; no custom networks):

```yaml
  auth-server:
    build: ./services/auth-server
    ports:
      - "127.0.0.1:8084:8085"
    environment:
      OAUTH_CLIENT_ID: devbot-agent
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET:-CHANGE_ME}
      DEMO_FIXTURES_ENABLED: "true"
    healthcheck:
      # Reason: auth-server is a dependency root (mcp-server waits on it),
      # so it gets a real healthcheck like postgres does.
      test: ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:8085/health')\""]
      interval: 5s
      timeout: 5s
      retries: 5
```

(`python -c` is used because `python:3.11-slim` has no curl; do not add curl to the
image just for the healthcheck.)

**Modify `.env.example`** — append:

```
# MCP / OAuth (authenticated MCP server — see docs/plans/authenticated-mcp/)
MCP_ENABLED=false
MCP_SERVER_URL=http://mcp-server:9000/mcp
OAUTH_TOKEN_URL=http://auth-server:8085/token
OAUTH_CLIENT_ID=devbot-agent
OAUTH_CLIENT_SECRET=CHANGE_ME
OAUTH_SCOPE=tools:read tools:execute tools:write
AUTH_FAILURE_MODE=fail_closed
JWKS_CACHE_TTL=300
```

**Modify `.github/workflows/ci.yml`** — add to the `tests` job, after the demo-cli
step:

```yaml
      - name: auth-server tests
        working-directory: services/auth-server
        run: |
          pip install -r requirements-dev.txt
          python -m pytest tests/ -v
```

**Modify `.gitleaks.toml`** — no new allowlist strings are expected (`CHANGE_ME` is
already allowlisted); **verify** by running gitleaks (below). If any new test literal
trips it, prefer renaming the literal over widening the allowlist. Never commit PEM
or JWK private material anywhere — tests must generate keys at runtime.

**Verify commands:**

```bash
docker compose up -d auth-server && sleep 3
curl -s http://127.0.0.1:8084/health
curl -s http://127.0.0.1:8084/.well-known/jwks.json
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect -s /repo --no-git -c /repo/.gitleaks.toml
```

**Scripted-mode preservation:** nothing in this phase touches devbot-agent; existing
suites unaffected. Run them anyway:
`cd services/devbot-agent && python -m pytest tests/ -v`.

---

## Phase 2 — mcp-server service (resource server + verifier)

### Task 2.1 — Scaffold

**Create (new):** `services/mcp-server/Dockerfile` (same pattern; `EXPOSE 9000`;
`CMD ["python", "-m", "src.server"]`), `services/mcp-server/requirements.txt`:

```
fastmcp>=2.11,<3.0
PyJWT[crypto]==2.10.1
psycopg2-binary==2.9.10
httpx==0.28.1
pydantic==2.10.4
pydantic-settings==2.7.1
```

`services/mcp-server/requirements-dev.txt` (`-r requirements.txt` + `pytest==8.3.4`),
`src/__init__.py`, `tests/__init__.py`.

### Task 2.2 — Config

**Create (new):** `services/mcp-server/src/config.py`:

```python
"""MCP-server configuration using pydantic settings."""

from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Resource-server settings loaded from environment variables."""

    # Canonical identifiers (TM-11)
    oauth_issuer: str = "http://auth-server:8085"
    jwks_url: str = "http://auth-server:8085/.well-known/jwks.json"
    canonical_uri: str = "http://mcp-server:9000/mcp"  # == aud

    # Enforcement toggles
    auth_mode: Literal["enforce", "off"] = "enforce"       # demo act 1 (off) vs acts 2-3 (enforce)
    auth_failure_mode: Literal["fail_closed", "fail_open"] = "fail_closed"  # TM-08/§4

    jwks_cache_ttl: int = 300
    clock_leeway_seconds: int = 30

    # Upstream credentials — the SERVER'S OWN, never the inbound token (TM-13)
    database_url: str = "postgresql://devbot:devbot_secret@postgres:5432/api_docs"
    customers_database_url: str = "postgresql://devbot:devbot_secret@postgres:5432/customers"
    github_pat: str = ""
    github_exfil_repo: str = "attacker-org/diagnostics"

    mcp_host: str = "0.0.0.0"
    mcp_port: int = 9000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
```

### Task 2.3 — Tools module (extraction, not move)

**Create (new):** `services/mcp-server/src/tools.py` — copy the four functions verbatim
from `services/devbot-agent/src/tools.py` (`query_database`, `fetch_webpage`,
`execute_command`, `github_create_issue`), changing only the import to the new
`src.config.settings`. **devbot-agent keeps its own copy unchanged** — this is a copy
for the extracted service, not a move, so scripted/in-process mode still works.

Add a header comment: `# Reason: upstream calls use THIS server's own creds, never the
inbound bearer token (TM-13, MCP token-passthrough prohibition).`

### Task 2.4 — The hand-written verifier (primary enforcement point)

**Create (new):** `services/mcp-server/src/verifier.py` (~80 lines, the teaching
centerpiece). It must contain, in plain readable Python:

- A `_JWKSCache` wrapping `jwt.PyJWKClient(settings.jwks_url,
  cache_keys=True, lifespan=settings.jwks_cache_ttl)` with **last-known-good** keys kept
  past TTL and a **circuit breaker** (open after 3 consecutive fetch failures, half-open
  probe after 30 s; a background retry every 15 s). Expose breaker state for `/health`.
- `verify_token(token: str) -> Claims` performing checks **in this order**, each failure
  raising a typed error the server maps to `401` with
  `WWW-Authenticate: Bearer resource_metadata="http://mcp-server:9000/.well-known/oauth-protected-resource", error="invalid_token"`:
  1. parse header; **`alg` must be in the hardcoded `{"RS256"}` allowlist** passed
     explicitly to `jwt.decode(algorithms=["RS256"])` — rejects `none` and HS256
     confusion by construction (TM-10).
  2. sanitize `kid` (length-cap 128, charset `[A-Za-z0-9_-]`); use **only** as a dict
     key into the JWKS cache — never a path/query/shell (TM-06). Unknown kid → at most
     **one** rate-limited refetch.
  3. verify signature against the resolved key.
  4. `iss` exact, case-sensitive `== settings.oauth_issuer` (TM-01); `jku`/`x5u`
     headers ignored entirely (TM-07).
  5. `settings.canonical_uri in aud` (TM-11).
  6. `exp`/`nbf` with `clock_leeway_seconds` (TM-12).
  7. `typ == "at+jwt"`.
- **The fail policy, as exactly one visible branch (§4, TM-08):** reached only when the
  `kid` cannot be resolved because the cache has no usable key AND a live fetch just
  failed. `fail_closed` → raise `AuthUnavailable` (→ 503 + `Retry-After: 30`, structured
  log `{"event": "auth_unavailable", "policy": "fail_closed", "reason":
  "jwks_unavailable", "kid": ...}`). `fail_open` → run steps 4–7 (every non-signature
  check) and if they pass, accept, emit `{"event": "auth_degraded_accept", "policy":
  "fail_open", "reason": "jwks_unavailable", "sub": ..., "jti": ...}` and set response
  header `X-Auth-Degraded: true`. **Expired tokens are 401 in both modes** (clock math
  needs no IdP). Keep the production shortcut — `FastMCP`'s built-in `JWTVerifier` — in a
  6-line comment labelled "what you'd write in production".
- Logging rule (TM-16): log `sub`/`jti`/`kid`/reason, **never the raw token**.

**Acceptance:** unit tests in Task 2.7 drive every branch via the Phase 1 fixtures.

### Task 2.5 — Scope map and dispatch (TM-14)

**Create (new):** `services/mcp-server/src/authz.py`:

```python
# Reason: default-deny — a tool missing from this map is never dispatchable.
TOOL_SCOPES: dict[str, str] = {
    "query_database": "tools:read",
    "fetch_webpage": "tools:read",
    "execute_command": "tools:execute",
    "github_create_issue": "tools:write",
}


def require_scope(tool_name: str, granted_scopes: set[str]) -> None:
    """Raise InsufficientScope unless the token carries the tool's scope.

    Args:
        tool_name (str): Canonical tool name being dispatched.
        granted_scopes (set[str]): Scopes parsed from the validated token.

    Raises:
        UnknownTool: If the tool is not in TOOL_SCOPES (default-deny).
        InsufficientScope: If the required scope is absent.
    """
```

`InsufficientScope` → `403` + `WWW-Authenticate: Bearer error="insufficient_scope",
scope="<required>"`. A test enumerates every registered FastMCP tool against
`TOOL_SCOPES` so adding a tool without a scope entry fails CI.

### Task 2.6 — FastMCP server + RFC 9728 metadata

**Create (new):** `services/mcp-server/src/server.py`:

- Build a `FastMCP` app over **streamable HTTP** at path `/mcp`, registering the four
  tools from `src.tools`.
- Plug the verifier into FastMCP's auth hook so every request is authenticated
  **per request** (TM-15: a reused session with an expired token still gets 401), then
  `require_scope` at dispatch.
- When `settings.auth_mode == "off"`, skip verification entirely (the **Act 1** "control
  off" state — an unauthenticated/forged request reaches the tools). **Act mapping
  (canonical, matches THREAT_MODEL TM-19):** Act 1 = `AUTH_MODE=off`; Act 2 =
  `AUTH_MODE=enforce` with the full scope ceiling (`tools:read tools:execute
  tools:write`) — every check passes and the injected kill chain still runs; Act 3 =
  `AUTH_MODE=enforce` with the agent's `OAUTH_SCOPE` narrowed to `tools:read`, so the
  same injected calls die with 403 `insufficient_scope` (and forged tokens with 401).
- Serve `GET /.well-known/oauth-protected-resource` (RFC 9728) naming the issuer and the
  canonical resource URI; unauthenticated requests to `/mcp` get `401` + the same
  `WWW-Authenticate` challenge pointing at this metadata URL.
- `GET /health` → `{"status": "ok", "auth_mode": ..., "auth_failure_mode": ...,
  "breaker": "<closed|open|half_open>"}` for the demo panel.

### Task 2.7 — Negative-path tests (threat-model-driven)

**Create (new):** `services/mcp-server/tests/test_verifier.py`,
`services/mcp-server/tests/test_authz.py`, `services/mcp-server/tests/test_server.py`.
Repo style (no fixtures/conftest; `@patch` for settings; generate keys at runtime; drive
broken tokens by constructing them the way Phase 1's `/demo/mint-broken` does so the two
agree). Required cases:

| Case | Expect | TM |
|---|---|---|
| valid token, correct scope | 200, tool runs | — |
| `alg=none` | 401 | TM-10 |
| HS256/RS256 confusion | 401 | TM-10 |
| wrong `aud` | 401 | TM-11 |
| wrong `iss` | 401 | TM-01 |
| expired (both failure modes) | 401 | TM-12 |
| `nbf` in future | 401 | TM-12 |
| boundary: `exp` at leeway ±1 s | accept / reject | TM-12 |
| hostile `kid` (traversal/huge) | clean 401, no side effect | TM-06 |
| no token | 401 + `WWW-Authenticate` | TM-15 |
| valid `tools:read` token calls `execute_command` | 403 `insufficient_scope` | TM-14 |
| tool missing from scope map | denied (default-deny) | TM-14 |
| **JWKS unreachable + cold cache, `fail_closed`** | 503 + `Retry-After` | TM-08 |
| **JWKS unreachable + cold cache, `fail_open`** | 200 + `X-Auth-Degraded: true` + audit log | TM-08 |
| JWKS unreachable + **warm cache** | 200 (last-known-good), not a policy event | TM-08 |
| upstream call carries no inbound `Authorization` | asserted absent | TM-13 |
| logs never contain the raw token | grep-shaped assertion over captured logs | TM-16 |

**Verify command:**

```bash
cd services/mcp-server && pip install -r requirements-dev.txt && python -m pytest tests/ -v
```

### Task 2.8 — Compose + CI

**Modify `docker-compose.yml`** — add:

```yaml
  mcp-server:
    build: ./services/mcp-server
    ports:
      - "127.0.0.1:8085:9000"
    environment:
      OAUTH_ISSUER: http://auth-server:8085
      JWKS_URL: http://auth-server:8085/.well-known/jwks.json
      CANONICAL_URI: http://mcp-server:9000/mcp
      AUTH_MODE: enforce
      AUTH_FAILURE_MODE: ${AUTH_FAILURE_MODE:-fail_closed}
      JWKS_CACHE_TTL: ${JWKS_CACHE_TTL:-300}
      DATABASE_URL: postgresql://devbot:devbot_secret@postgres:5432/api_docs
      CUSTOMERS_DATABASE_URL: postgresql://devbot:devbot_secret@postgres:5432/customers
      GITHUB_PAT: ${GITHUB_PAT:-}
    depends_on:
      auth-server:
        condition: service_healthy
      postgres:
        condition: service_healthy
    healthcheck:
      test: ["CMD-SHELL", "python -c \"import urllib.request;urllib.request.urlopen('http://localhost:9000/health')\""]
      interval: 5s
      timeout: 5s
      retries: 5
```

Add the CI step mirroring Phase 1's (working-directory `services/mcp-server`).

**Scripted-mode preservation:** devbot-agent still imports its own `src/tools.py`;
`mcp-server` is a new, independent service. Existing devbot-agent and demo-cli suites
unchanged. Re-run them to confirm.

---

## Phase 3 — Agent client integration (behind `mcp_enabled`, default off)

### Task 3.1 — Settings

**Modify `services/devbot-agent/src/config.py`** — add fields (all with safe defaults so
the ~1150 lines of settings-patching tests keep passing):

```python
    # --- Authenticated MCP (default OFF; scripted mode never needs these) ---
    mcp_enabled: bool = False
    mcp_server_url: str = "http://mcp-server:9000/mcp"
    oauth_token_url: str = "http://auth-server:8085/token"
    oauth_client_id: str = "devbot-agent"
    oauth_client_secret: str = "CHANGE_ME"
    oauth_scope: str = "tools:read tools:execute tools:write"
    auth_failure_mode: Literal["fail_closed", "fail_open"] = "fail_closed"
    jwks_cache_ttl: int = 300
```

### Task 3.2 — The OAuth client-credentials client

**Create (new):** `services/devbot-agent/src/auth.py` — `OAuthClientCredentialsClient`
(httpx is already a dependency):

- `get_token() -> str`: POST `grant_type=client_credentials` to `oauth_token_url` with
  `client_secret_basic`, `scope=settings.oauth_scope`, and
  `resource=settings.mcp_server_url` (RFC 8707).
- **Cache** keyed by `(token_url, client_id, scope, resource)`; **proactive refresh at
  `exp − 30 s`** (TM-05); **single-flight lock** (`asyncio.Lock` or `threading.Lock`) so
  concurrent tool calls make one token request (TM-05).
- No refresh tokens (client-credentials has none — re-request is the refresh).
- Token held **in memory only**, never logged, never placed in a URL (TM-17).

**Create (new):** `services/devbot-agent/tests/test_auth.py` — repo style, mock httpx:
cache hit avoids a second POST; expiry triggers refetch; single-flight (two concurrent
calls → one POST); token never appears in any logged string. Expected/edge/failure
cases per conventions.

### Task 3.3 — Wire MCP transport into the live agent

**Modify `services/devbot-agent/src/agent.py`:**

- Add `langchain-mcp-adapters` import **lazily inside** the live branch so scripted mode
  (and tests that never set `mcp_enabled`) never import it.
- In `create_agent` (or a new helper called from it), when
  `settings.mcp_enabled` is `True`: build `MultiServerMCPClient` with transport
  `streamable_http`, URL `settings.mcp_server_url`, and
  `headers={"Authorization": f"Bearer {token}"}` from `src.auth`; bind the loaded remote
  tools instead of `_get_langchain_tools()`.
- When `settings.mcp_enabled` is `False` (default), behavior is **exactly today's** —
  `_get_langchain_tools()` + in-process `_execute_tool`.
- **Document the static-headers caveat** in a `# Reason:` comment: langchain's MCP client
  takes headers at construction, so on token expiry the client is rebuilt (acceptable at
  this lab's scale).

**Modify `services/devbot-agent/requirements.txt`** — add the pinned
`langchain-mcp-adapters` line with the migration comment from §2.

### Task 3.4 — Env / compose / secrets wiring

**Modify `docker-compose.yml`** (devbot-agent service) — add env:

```yaml
      MCP_ENABLED: ${MCP_ENABLED:-false}
      MCP_SERVER_URL: http://mcp-server:9000/mcp
      OAUTH_TOKEN_URL: http://auth-server:8085/token
      OAUTH_CLIENT_ID: devbot-agent
      OAUTH_CLIENT_SECRET: ${OAUTH_CLIENT_SECRET:-CHANGE_ME}
      OAUTH_SCOPE: ${OAUTH_SCOPE:-tools:read tools:execute tools:write}
      AUTH_FAILURE_MODE: ${AUTH_FAILURE_MODE:-fail_closed}
```

and `depends_on: mcp-server: {condition: service_started}` (service_started, not
service_healthy — the agent must still boot when MCP is off).

**Known trade-off (document, don't silently accept):** even `service_started` means a
failed mcp-server *image build* blocks `docker compose up devbot-agent`, slightly
weakening the "scripted mode needs zero auth containers" invariant (Task 8.3 only
achieves it by stopping the containers post-start). Add a `# Reason:` comment on the
`depends_on` entry and a line in README/DEMO.md (Task 7.1) stating that scripted-only
users can bypass the dependency entirely with
`docker compose up devbot-agent --no-deps` (plus its own real deps, e.g. postgres, as
today).

`.env.example` already updated in Phase 1 (Task 1.6). Confirm `.gitleaks.toml` still
green.

### Task 3.5 — Regression gate

**Acceptance:** the **entire existing devbot-agent suite passes untouched** plus the new
`test_auth.py`. If any existing test breaks, the default-off wiring is wrong — fix the
wiring, not the test.

**Verify command:**

```bash
cd services/devbot-agent && pip install -r requirements-dev.txt && python -m pytest tests/ -v
```

**Scripted-mode preservation:** `mcp_enabled=False` means no network, no new imports on
the scripted path; `_execute_tool` and the in-process tools are untouched.

---

## Phase 4 — Demo narrative wiring (scripted + live outage)

### Task 4.1 — Scripted auth-denial beats

**Modify `services/devbot-agent/src/scripted.py`** — add new steps shaped exactly like
the existing `_ACT3_FLOW` entries (`blocked: True`, `override_result`, `auto_advance`),
so they need no auth server. Two new denial beats to interleave with the Sentinel
denials:

- a **401 `invalid_token`** beat (e.g. a forged/`alg=none` token rejected), text in the
  style of the existing Sentinel strings:
  `"[AUTH DENIED — MCP Verifier] 401 invalid_token: alg 'none' not in allowlist {RS256}
  (RFC 8725). Request rejected before tool dispatch."`
- a **403 `insufficient_scope`** beat on `execute_command`:
  `"[AUTH DENIED — MCP Verifier] 403 insufficient_scope: 'execute_command' requires
  'tools:execute'; token carries only 'tools:read'. WWW-Authenticate: scope=tools:execute."`

These make TM-10 and TM-14 teachable offline.

### Task 4.2 — Act state machine ties auth on/off

**Modify `services/devbot-agent/src/main.py`** (`/set-act` + WebSocket `set_act`) — when
`mcp_enabled` and live, apply the canonical act mapping from Task 2.6: **Act 1** runs
with `AUTH_MODE=off` (the "control off" state — a forged/absent token still reaches the
tools); **Act 2** runs with auth **enforced and the full scope ceiling**, so every
signature/claim/scope check passes and the injected kill chain still succeeds — the
TM-19 confused-deputy demonstration; **Act 3** keeps auth enforced but narrows the
agent's `OAUTH_SCOPE` to `tools:read`, so the same injected `execute_command` dies with
403 `insufficient_scope` (alongside the 401 `invalid_token` beat). In scripted mode the beats from
Task 4.1 carry the narrative with no behavior change needed to the state machine beyond
selecting the new steps. Keep the `:8000` surface and nginx proxies unchanged.

**Modify `services/devbot-agent/tests/test_scripted.py`** — add tests asserting the new
401/403 steps return `blocked: True` with the expected `override_result` text.

### Task 4.3 — Live fail-policy outage demo

**Modify:** `services/demo-cli/src/cli.py` (existing file) — add an `auth-outage`
command in the file's existing Click style, and document a manual sequence in DEMO.md:

1. `JWKS_CACHE_TTL=60`; `docker compose stop auth-server` → tool calls **still succeed**
   on cached keys (warm cache; TM-08 primary mitigation — show this first).
2. `docker compose restart mcp-server` (cold cache): `fail_closed` → agent tool call
   surfaces **503**; flip `AUTH_FAILURE_MODE=fail_open`, restart → **same call succeeds**,
   show the `auth_degraded_accept` log and `X-Auth-Degraded: true` header side by side.
3. `docker compose start auth-server` → breaker half-opens then closes; normal 401/403
   resume. Breaker state visible on `mcp-server /health`.

**Modify `services/demo-cli/tests/test_cli.py`** — test the new command's wiring
(mock the HTTP calls; no live containers in CI).

**Verify commands:**

```bash
cd services/devbot-agent && python -m pytest tests/ -v
cd services/demo-cli && python -m pytest tests/ -v
```

**Scripted-mode preservation:** Task 4.1/4.2 are additive scripted steps; the offline
demo gains the auth beats and loses nothing.

---

## Phase 5 — Optional agentgateway profile (defense-in-depth contrast)

### Task 5.0 — Verify the image pin and config surface (do this first)

The §2 pin, the "config surface moved v1.4→v1.5" note, and the
`mcpAuthentication`/`mcpAuthorization` key names below were taken from upstream docs
during planning and **cannot be verified from this repo**. Before Task 5.1:

1. `docker pull cr.agentgateway.dev/agentgateway:v1.5.0` — if it fails, check
   `ghcr.io/agentgateway/agentgateway` and the upstream releases page
   (<https://github.com/agentgateway/agentgateway>) for the current registry and tag
   scheme (historically `0.x` tags on ghcr.io), and update §2, this phase, and the
   compose snippet in Task 5.2 to the verified reference.
2. Confirm the MCP authn/authz config key names (`mcpAuthentication`,
   `mcpAuthorization`, CEL rule fields) against the docs for the exact version pulled;
   if they differ, use the documented names and record the correction in the config
   file's header comment.

### Task 5.1 — Gateway config

**Create (new):** `services/agentgateway/config.yaml` — a simplified MCP config:

- an `mcp` target fronting `http://mcp-server:9000/mcp` as a streamable-HTTP backend;
- `mcpAuthentication` (`mode: strict`) with issuer/JWKS fields pointed at the lab issuer
  (`http://auth-server:8085`, its `.well-known/jwks.json`), audience =
  `http://mcp-server:9000/mcp`;
- `mcpAuthorization` CEL rules keyed on `mcp.tool.name` and the token's `scope` claim,
  mirroring `TOOL_SCOPES`.

Pin behavior to the version verified in Task 5.0 and note in a comment that the
config surface has moved between releases (verify key names against that version's
docs, per Task 5.0).

### Task 5.2 — Compose profile

**Modify `docker-compose.yml`** — add under `profiles: ["gateway"]` (substituting the
image reference verified in Task 5.0):

```yaml
  agentgateway:
    image: cr.agentgateway.dev/agentgateway:v1.5.0
    profiles: ["gateway"]
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - ./services/agentgateway/config.yaml:/etc/agentgateway/config.yaml:ro
    depends_on:
      mcp-server:
        condition: service_healthy
```

Off by default — the laptop stack stays at two extra containers unless
`docker compose --profile gateway up` is used.

### Task 5.3 — Docs for repointing

**Modify `docs/DEMO.md` / `README.md`** — snippet showing that with the profile up you
set the agent's `MCP_SERVER_URL=http://agentgateway:3000/mcp`; what changes (gateway
serves RFC 9728 metadata, filters `tools/list` via CEL, strips the token before the
backend) and what does not (same tokens, `aud` unchanged, mcp-server still runs its own
verifier so a direct-to-backend bypass still faces full checks — TM-21). State plainly
that agentgateway is **always fail-closed with no fail-open knob** (threat model §4
contrast).

**Verify command:**

```bash
docker compose --profile gateway config   # validates the compose file parses
```

**Scripted-mode preservation:** gateway is opt-in and off by default; no Python changes.

---

## Phase 6 — Deployment parity (k8s + Helm)

### Task 6.1 — k8s manifests

**Create (new):** `k8s/auth-server.yaml`, `k8s/mcp-server.yaml` — mirror
`k8s/devbot-agent.yaml`: Deployment + ClusterIP in namespace `ai-agents`, labels
`app.kubernetes.io/name` + `app.kubernetes.io/part-of: agent-security-lab`,
`imagePullPolicy: IfNotPresent`, `readinessProbe httpGet /health`, `envFrom`
configMap/secret. Resources: auth-server `128Mi/100m`, mcp-server `256Mi/250m`. Set
`DEMO_FIXTURES_ENABLED: "false"` for auth-server in k8s (TM-03). No `NET_RAW` for these.

**Create (new):** `k8s/agentgateway.yaml` — fully commented-out optional manifest.

**Modify `k8s/configmap.yaml`** — add non-secret keys: `MCP_ENABLED`, `MCP_SERVER_URL`,
`OAUTH_TOKEN_URL`, `OAUTH_ISSUER`, `JWKS_URL`, `CANONICAL_URI`, `OAUTH_SCOPE`,
`AUTH_MODE`, `AUTH_FAILURE_MODE`, `JWKS_CACHE_TTL`.

**Modify `k8s/secrets.yaml`** — add `OAUTH_CLIENT_SECRET: Q0hBTkdFX01F` (base64
`CHANGE_ME`). No new gitleaks allowlist entry needed (`Q0hBTkdFX01F` already allowlisted).

### Task 6.2 — Helm parity

**Create (new):** `helm/agent-security-lab/templates/auth-server.yaml`,
`helm/agent-security-lab/templates/mcp-server.yaml` — templated mirrors.
**Modify** `helm/agent-security-lab/values.yaml` and `values-local.yaml` — add
`config:`/`secrets:`/`resources:` blocks for both services and the base64 `CHANGE_ME`
client secret. Add a commented optional agentgateway block.

**Verify commands:**

```bash
kubectl apply --dry-run=client -f k8s/auth-server.yaml -f k8s/mcp-server.yaml
helm template helm/agent-security-lab | head -n 50   # renders without error
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect -s /repo --no-git -c /repo/.gitleaks.toml
```

**Scripted-mode preservation:** manifests are deploy-time only; no code path changes.

---

## Phase 7 — Threat model cross-links, docs, executive summary

> The STRIDE threat model already exists at
> [`docs/plans/authenticated-mcp/THREAT_MODEL.md`](./THREAT_MODEL.md). This phase does
> **not** rewrite it — it cross-links the implemented mitigations and updates the lab's
> standing docs.

### Task 7.1 — Extend standing docs

- **Modify `docs/ARCHITECTURE.md`** — add the authenticated-MCP control to the kill-chain
  control mapping (token boundary, scope-bounded blast radius) and reference TM-19's
  honest framing: *auth narrows what a hijacked agent reaches; it does not stop the
  hijack.*
- **Modify `SECURITY.md`** — add invariants: 127.0.0.1-only on the two new ports; toy
  issuer never for production; `/demo/mint-broken` disabled outside the lab
  (`DEMO_FIXTURES_ENABLED=false` in k8s); private keys generated at runtime, never
  committed.
- **Modify `docs/DEMO.md`** — add the auth act beats (401/403 in Act 3) and the
  fail-policy outage demo from Phase 4; note the container-boundary nuance of TM-17
  (the agent's own shell can read `OAUTH_CLIENT_SECRET` in in-process mode).
- **Modify `README.md`** — one paragraph + the `docker compose up` note that the two new
  services are default-on but `MCP_ENABLED=false` keeps the agent on the in-process path.

### Task 7.2 — Executive summary

**Create (new):** `docs/plans/authenticated-mcp/EXECUTIVE_SUMMARY.md` (if the planning
workflow already produced this file, update it to match what was actually implemented
instead of recreating it) — ≤2 pages for a non-implementer: what was built and why the in-framework verifier beats a gateway/IdP
for a built-to-be-read lab; the fail-open/fail-closed trade in one table; the top-5
risks from THREAT_MODEL §5; cost (two `python:3.11-slim` containers, agentgateway
opt-in); and the headline lesson (TM-19).

**Verify:** markdown links resolve (`grep -o '](\.\./[^)]*)' docs/plans/authenticated-mcp/*.md`
and confirm each target exists).

---

## Phase 8 — Verification pass

### Task 8.1 — Full CI green

```bash
for svc in auth-server mcp-server devbot-agent demo-cli; do
  (cd services/$svc && pip install -r requirements-dev.txt && python -m pytest tests/ -v) || echo "FAIL: $svc"
done
docker run --rm -v "$(pwd):/repo" zricethezav/gitleaks:latest detect -s /repo --no-git -c /repo/.gitleaks.toml
```

All four suites pass; gitleaks clean.

### Task 8.2 — End-to-end smoke (live)

```bash
docker compose up -d --build && sleep 5

# Helper: POST a JSON-RPC tools/call to mcp-server with a bearer token, print HTTP status.
mcp_status() {  # $1 = token, $2 = tool name
  curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $1" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$2\",\"arguments\":{}}}" \
    http://127.0.0.1:8085/mcp
}

# Happy path: full-scope token -> 200 (or the MCP session-handshake status the
# implementation settles on — assert whatever "authenticated and dispatched" is).
TOKEN=$(curl -s -u devbot-agent:CHANGE_ME -d 'grant_type=client_credentials' \
  http://127.0.0.1:8084/token | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
code=$(mcp_status "$TOKEN" query_database)
[ "$code" = "200" ] || echo "FAIL happy path: expected 200, got $code"

# Each broken variant, PRESENTED TO mcp-server, must be rejected 401:
for v in none hs256-confusion wrong-aud wrong-iss expired hostile-kid; do
  BAD=$(curl -s "http://127.0.0.1:8084/demo/mint-broken?variant=$v" \
    | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
  code=$(mcp_status "$BAD" query_database)
  [ "$code" = "401" ] || echo "FAIL variant $v: expected 401, got $code"
done

# Scope 403: a tools:read token calling execute_command:
RO=$(curl -s -u devbot-agent:CHANGE_ME -d 'grant_type=client_credentials&scope=tools:read' \
  http://127.0.0.1:8084/token | python -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
code=$(mcp_status "$RO" execute_command)
[ "$code" = "403" ] || echo "FAIL scope check: expected 403, got $code"

# Fail-policy contrast (uses $TOKEN minted above — still valid, now unverifiable):
docker compose stop auth-server
docker compose restart mcp-server && sleep 5          # cold cache, fail_closed default
code=$(mcp_status "$TOKEN" query_database)
[ "$code" = "503" ] || echo "FAIL fail_closed: expected 503, got $code"
AUTH_FAILURE_MODE=fail_open docker compose up -d mcp-server && sleep 5
curl -s -D - -o /dev/null -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"query_database","arguments":{}}}' \
  http://127.0.0.1:8085/mcp | grep -i '^X-Auth-Degraded: true' \
  || echo "FAIL fail_open: expected X-Auth-Degraded: true header"
docker compose start auth-server
```

Confirm: no `FAIL` lines — happy path 200; every broken token 401 **at mcp-server**;
scope mismatch 403; `fail_closed` 503 vs `fail_open` degraded-accept with
`X-Auth-Degraded: true`. If FastMCP requires an `initialize` handshake before
`tools/call`, extend `mcp_status` with that first call — the asserted status codes
are the contract; the exact request shape may track the implementation.

### Task 8.3 — Scripted offline run (no auth containers)

```bash
docker compose stop auth-server mcp-server
# with DEMO_MODE=scripted, run Act 3 — the 401/403 auth beats render via override_result
cd services/devbot-agent && python -m pytest tests/ -v
```

Confirm scripted Act 3 shows the auth-denial beats with **no auth containers running**.
Also verify the stronger form from Task 3.4: `docker compose up devbot-agent --no-deps`
(plus its pre-existing deps) boots the agent without the auth images at all.

### Task 8.4 — Secret hygiene final check

Every new secret-shaped string is a placeholder (`CHANGE_ME` / `Q0hBTkdFX01F`) and
allowlisted; no PEM/JWK private material anywhere in the tree; `scripts/pre-commit`
still blocks a staged `.env`.

---

## Task-level dependency note

- **Phase 1 → Phase 2:** mcp-server's tests consume Phase 1's broken-token constructions
  (keep them in sync; both encode the same six defects).
- **Phase 2 → Phase 3:** the agent client needs a running mcp-server contract (URL,
  Bearer header, 401/403 semantics) to integrate against.
- **Phase 3 → Phase 4:** the live outage demo (4.3) needs the client (3.2) + enforcement
  (2.4); the scripted beats (4.1) depend on nothing and can land anytime after Phase 0.
- **Phases 1–4 → Phase 5:** agentgateway fronts a working mcp-server.
- **Phases 1–3 → Phase 6:** manifests mirror finalized compose env.
- **All → Phase 7/8:** docs and verification last.
- **Independent / parallelizable:** 4.1 (scripted beats), 7.1 doc stubs, and the
  executive summary draft can proceed alongside implementation.

Each phase keeps scripted/offline mode green; **run the devbot-agent + demo-cli suites at
the end of every phase**, not just Phase 8.

## Rough per-phase effort

| Phase | Effort | Notes |
|---|---|---|
| 1 auth-server | ~1 day | ~100 LOC issuer + keys + fixtures + tests |
| 2 mcp-server | ~2 days | verifier + breaker + fail policy + full negative-path suite (the heart) |
| 3 agent client | ~1 day | auth.py + lazy MCP wiring; the regression gate is the real work |
| 4 demo wiring | ~1 day | scripted beats + outage demo + CLI command |
| 5 agentgateway | ~0.5 day | one YAML + compose profile + docs; opt-in |
| 6 deploy parity | ~1 day | k8s + Helm mirrors |
| 7 docs + exec summary | ~0.5 day | cross-links + summary |
| 8 verification | ~0.5 day | smoke + offline + hygiene |

**Total: ~7–8 engineer-days.** Phase 2 carries the most risk (verifier correctness,
circuit-breaker/fail-policy branch) and deserves the most review.
