#!/usr/bin/env bash

set -euo pipefail

BASE_URL="${1:-${BASE_URL:-http://127.0.0.1:8000}}"
ADMIN_TOKEN="${ADMIN_API_TOKEN:-}"
WRITE_SMOKE="${WRITE_SMOKE:-0}"
EA_TOKEN="${EA_API_TOKEN:-}"
SMOKE_EA_ID="${SMOKE_EA_ID:-production-smoke-ea}"

if [[ -z "$ADMIN_TOKEN" ]]; then
  echo "ERROR: ADMIN_API_TOKEN is required." >&2
  exit 1
fi

curl_json() {
  local method="$1"
  local path="$2"
  shift 2
  curl -fsS -X "$method" "$BASE_URL$path" "$@"
}

echo "BASE_URL=$BASE_URL"
echo "WRITE_SMOKE=$WRITE_SMOKE"

echo ""
echo "1. Health check"
curl_json GET "/health"
echo ""

echo ""
echo "2. Admin pages are reachable"
curl -fsS "$BASE_URL/admin" -o /dev/null
curl -fsS "$BASE_URL/ea-accounts" -o /dev/null
curl -fsS "$BASE_URL/users" -o /dev/null
curl -fsS "$BASE_URL/commands" -o /dev/null
curl -fsS "$BASE_URL/audit-logs" -o /dev/null
echo "OK"

echo ""
echo "3. Admin API authentication"
curl_json GET "/api/admin/eas" -H "X-Admin-Token: $ADMIN_TOKEN" >/dev/null
echo "OK"

echo ""
echo "4. System checks"
SYSTEM_CHECKS=$(curl_json GET "/api/admin/system-checks" -H "X-Admin-Token: $ADMIN_TOKEN")
echo "$SYSTEM_CHECKS"
SYSTEM_STATUS=$(python3 -c "import json,sys; print(json.load(sys.stdin)['status'])" <<< "$SYSTEM_CHECKS")
if [[ "$SYSTEM_STATUS" == "error" ]]; then
  echo "ERROR: system checks returned error status." >&2
  exit 1
fi

echo ""
echo "5. Read-only API checks"
curl_json GET "/api/admin/commands?limit=1" -H "X-Admin-Token: $ADMIN_TOKEN" >/dev/null
curl_json GET "/api/admin/audit-logs?limit=1" -H "X-Admin-Token: $ADMIN_TOKEN" >/dev/null
curl_json GET "/api/admin/safety-config" -H "X-Admin-Token: $ADMIN_TOKEN" >/dev/null
echo "OK"

if [[ "$WRITE_SMOKE" != "1" ]]; then
  echo ""
  echo "Read-only production smoke test finished."
  echo "Set WRITE_SMOKE=1 and EA_API_TOKEN to run optional write checks with SMOKE_EA_ID=$SMOKE_EA_ID."
  exit 0
fi

if [[ -z "$EA_TOKEN" ]]; then
  echo "ERROR: EA_API_TOKEN is required when WRITE_SMOKE=1." >&2
  exit 1
fi

echo ""
echo "6. Optional write check: EA heartbeat"
curl_json POST "/api/ea/heartbeat" \
  -H "Content-Type: application/json" \
  -H "X-EA-Token: $EA_TOKEN" \
  -d "{
    \"ea_id\": \"$SMOKE_EA_ID\",
    \"account_number\": \"production-smoke\",
    \"broker\": \"Smoke Test\",
    \"terminal\": \"MT5\",
    \"strategy_name\": \"Production Smoke\",
    \"version\": \"1.0\",
    \"status\": \"online\",
    \"allow_trading\": false
  }" >/dev/null
echo "OK"

echo ""
echo "7. Optional write check: create and cancel update_params command"
COMMAND_RESPONSE=$(curl_json POST "/api/admin/commands" \
  -H "Content-Type: application/json" \
  -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d "{
    \"ea_id\": \"$SMOKE_EA_ID\",
    \"command_type\": \"update_params\",
    \"payload\": {\"smoke_test\": true},
    \"requested_by\": \"production-smoke-test\"
  }")
echo "$COMMAND_RESPONSE"
COMMAND_ID=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<< "$COMMAND_RESPONSE")
curl_json POST "/api/admin/commands/$COMMAND_ID/cancel" -H "X-Admin-Token: $ADMIN_TOKEN" >/dev/null
echo "Command $COMMAND_ID cancelled."

echo ""
echo "Production smoke test finished."
