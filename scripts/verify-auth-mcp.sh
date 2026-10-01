#!/usr/bin/env bash
# End-to-end live smoke for the authenticated MCP server (Task 8.2).
#
# Requires a running Docker daemon. The implementation loop could not run this
# in its sandbox (no daemon), so it is captured here as a one-command check.
# Run from the repo root:  bash scripts/verify-auth-mcp.sh
#
# Asserts: happy-path 200; every broken token rejected 401 AT mcp-server;
# scope mismatch 403; fail_closed 503 vs fail_open X-Auth-Degraded: true.
set -u
fail=0

echo "==> docker compose up -d --build"
docker compose up -d --build || { echo "compose up failed"; exit 1; }
sleep 5

AUTH=http://127.0.0.1:8084
MCP=http://127.0.0.1:8085/mcp

tok() {  # $1 = extra form args; prints access_token
  curl -s -u devbot-agent:CHANGE_ME -d "grant_type=client_credentials${1:+&$1}" \
    "$AUTH/token" | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'
}

mcp_status() {  # $1 = token, $2 = tool -> prints HTTP status
  curl -s -o /dev/null -w '%{http_code}' \
    -H "Authorization: Bearer $1" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -d "{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",\"params\":{\"name\":\"$2\",\"arguments\":{}}}" \
    "$MCP"
}

TOKEN=$(tok "")
code=$(mcp_status "$TOKEN" query_database)
[ "$code" = "200" ] || { echo "FAIL happy path: expected 200, got $code"; fail=1; }

for v in none hs256-confusion wrong-aud wrong-iss expired hostile-kid; do
  BAD=$(curl -s "$AUTH/demo/mint-broken?variant=$v" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')
  code=$(mcp_status "$BAD" query_database)
  [ "$code" = "401" ] || { echo "FAIL variant $v: expected 401, got $code"; fail=1; }
done

RO=$(tok "scope=tools:read")
code=$(mcp_status "$RO" execute_command)
[ "$code" = "403" ] || { echo "FAIL scope check: expected 403, got $code"; fail=1; }

echo "==> fail-policy contrast"
docker compose stop auth-server
docker compose restart mcp-server && sleep 5          # cold cache, fail_closed default
code=$(mcp_status "$TOKEN" query_database)
[ "$code" = "503" ] || { echo "FAIL fail_closed: expected 503, got $code"; fail=1; }

AUTH_FAILURE_MODE=fail_open docker compose up -d mcp-server && sleep 5
curl -s -D - -o /dev/null -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"query_database","arguments":{}}}' \
  "$MCP" | grep -qi '^X-Auth-Degraded: true' \
  || { echo "FAIL fail_open: expected X-Auth-Degraded: true header"; fail=1; }
docker compose start auth-server

if [ "$fail" = "0" ]; then
  echo "ALL CHECKS PASSED"
else
  echo "ONE OR MORE CHECKS FAILED"
fi
exit "$fail"
