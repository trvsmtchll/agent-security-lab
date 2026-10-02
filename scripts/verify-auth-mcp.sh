#!/usr/bin/env bash
# End-to-end live smoke for the authenticated MCP server (Task 8.2).
#
# Requires a running Docker daemon. Run from the repo root:
#   bash scripts/verify-auth-mcp.sh
#
# Asserts: happy-path 200; every broken token rejected 401 AT mcp-server;
# scope mismatch 403; fail_closed 503 vs fail_open X-Auth-Degraded: true.
#
# mcp_call() performs the real MCP streamable-HTTP handshake (initialize ->
# notifications/initialized -> tools/call), because FastMCP rejects a bare
# tools/call with 400 "Missing session ID". Auth is enforced per request, so
# a bad token is rejected at the initialize step (401), a valid-but-unscoped
# token passes initialize and is denied at tools/call (403), and an
# unverifiable token under fail_closed yields 503 at initialize.
set -u
fail=0

echo "==> docker compose up -d --build"
docker compose up -d --build || { echo "compose up failed"; exit 1; }
sleep 5

AUTH=http://127.0.0.1:8084
MCP=http://127.0.0.1:8085/mcp
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
# Fixed path (not mktemp): mcp_call runs inside $(...) — a subshell — so a
# variable set there would not reach the parent; a file on disk does.
INIT_HDR=/tmp/mcp_init.hdr

tok() {  # $1 = extra form args; prints access_token
  curl -s -u devbot-agent:CHANGE_ME -d "grant_type=client_credentials${1:+&$1}" \
    "$AUTH/token" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'
}

# Full MCP handshake. Prints the operative HTTP status: the initialize status
# when that is not 200 (401/503), otherwise the tools/call status (200/403).
# Writes the initialize response headers to $INIT_HDR (for the X-Auth-Degraded check).
mcp_call() {  # $1 = token, $2 = tool
  local token="$1" tool="$2" sid icode
  icode=$(curl -s -D "$INIT_HDR" -o /dev/null -w '%{http_code}' -X POST "$MCP" \
    -H "Authorization: Bearer $token" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d "$INIT")
  if [ "$icode" != "200" ]; then echo "$icode"; return; fi
  sid=$(awk 'tolower($1)=="mcp-session-id:"{print $2}' "$INIT_HDR" | tr -d '\r')
  curl -s -o /dev/null -X POST "$MCP" \
    -H "Authorization: Bearer $token" -H "mcp-session-id: $sid" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  curl -s -o /dev/null -w '%{http_code}' -X POST "$MCP" \
    -H "Authorization: Bearer $token" -H "mcp-session-id: $sid" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"$tool\",\"arguments\":{}}}"
}

TOKEN=$(tok "")
code=$(mcp_call "$TOKEN" query_database)
[ "$code" = "200" ] || { echo "FAIL happy path: expected 200, got $code"; fail=1; }

for v in none hs256-confusion wrong-aud wrong-iss expired hostile-kid; do
  BAD=$(curl -s "$AUTH/demo/mint-broken?variant=$v" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
  code=$(mcp_call "$BAD" query_database)
  [ "$code" = "401" ] || { echo "FAIL variant $v: expected 401, got $code"; fail=1; }
done

RO=$(tok "scope=tools:read")
code=$(mcp_call "$RO" execute_command)
[ "$code" = "403" ] || { echo "FAIL scope check: expected 403, got $code"; fail=1; }

echo "==> fail-policy contrast"
# Cold cache + issuer outage. `restart` keeps fail_closed (the compose default)
# and does NOT start dependencies, so auth-server stays down.
docker compose stop auth-server
docker compose restart mcp-server && sleep 5
code=$(mcp_call "$TOKEN" query_database)
[ "$code" = "503" ] || { echo "FAIL fail_closed: expected 503, got $code"; fail=1; }

# Flip to fail_open WITHOUT restarting auth-server: --no-deps keeps the issuer
# down so the degraded-accept path actually triggers.
AUTH_FAILURE_MODE=fail_open docker compose up -d --no-deps mcp-server && sleep 5
code=$(mcp_call "$TOKEN" query_database)
if [ "$code" = "200" ] && grep -qi '^x-auth-degraded: *true' "$INIT_HDR"; then
  : # degraded-accept confirmed
else
  echo "FAIL fail_open: expected 200 + X-Auth-Degraded: true (got status $code)"; fail=1
fi

echo "==> restoring stack (auth-server up, mcp-server back to compose default)"
docker compose up -d >/dev/null 2>&1

if [ "$fail" = "0" ]; then
  echo "ALL CHECKS PASSED"
else
  echo "ONE OR MORE CHECKS FAILED"
fi
exit "$fail"
