#!/usr/bin/env bash
# End-to-end smoke test against a running `docker compose` stack (real Docker, PostgreSQL, runner, worker).
set -euo pipefail
API=${API:-http://localhost:8000}; WEB=${WEB:-http://localhost:8080}
JAR=$(mktemp); trap 'rm -f "$JAR"' EXIT
step() { echo "==> $*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

step "wait for API readiness"
for _ in $(seq 1 90); do curl -fsS "$API/ready" >/dev/null 2>&1 && break; sleep 2; done
curl -fsS "$API/ready" | grep -q '"database":"up"' || fail "API not ready"

EMAIL="e2e-$RANDOM@example.com"; PW="Correct-Horse-9"
step "register and login"
curl -fsS -X POST "$API/api/v1/auth/register" -H 'Content-Type: application/json' \
  -d "{\"organization\":\"E2E\",\"email\":\"$EMAIL\",\"password\":\"$PW\"}" >/dev/null
CSRF=$(curl -fsS -c "$JAR" -X POST "$API/api/v1/auth/login" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PW\"}" | jq -r .csrf_token)
[ -n "$CSRF" ] && [ "$CSRF" != null ] || fail "no csrf token"
req() { curl -fsS -b "$JAR" -H "X-CSRF-Token: $CSRF" "$@"; }

step "request without CSRF is rejected"
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -X POST "$API/api/v1/instances" -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: x' -d '{"name":"web-e2e","template":"alpine-small"}')
[ "$code" = 403 ] || fail "expected 403 without CSRF, got $code"

state() { req "$API/api/v1/instances/$1" | jq -r .state; }
wait_state() { for _ in $(seq 1 90); do [ "$(state "$1")" = "$2" ] && return 0; sleep 2; done; fail "instance $1 never reached $2 (is $(state "$1"))"; }

step "create instance (idempotent)"
IID=$(req -X POST "$API/api/v1/instances" -H 'Content-Type: application/json' -H 'Idempotency-Key: e2e-create' \
  -d '{"name":"web-e2e","template":"alpine-small"}' | jq -r .instance.id)
IID2=$(req -X POST "$API/api/v1/instances" -H 'Content-Type: application/json' -H 'Idempotency-Key: e2e-create' \
  -d '{"name":"web-e2e","template":"alpine-small"}' | jq -r .instance.id)
[ "$IID" = "$IID2" ] || fail "idempotency broken"
wait_state "$IID" running

step "container is really running and hardened"
C="novacloud-$IID"
[ "$(docker inspect -f '{{.State.Running}}' "$C")" = true ] || fail "container not running"
[ "$(docker inspect -f '{{.HostConfig.Privileged}}' "$C")" = false ] || fail "privileged container"
[ "$(docker inspect -f '{{.HostConfig.NetworkMode}}' "$C")" = none ] || fail "network not none"
docker inspect -f '{{.HostConfig.CapDrop}}' "$C" | grep -qi all || fail "capabilities not dropped"

step "stop, start"
req -X POST "$API/api/v1/instances/$IID/stop" -H 'Idempotency-Key: e2e-stop' >/dev/null; wait_state "$IID" stopped
req -X POST "$API/api/v1/instances/$IID/start" -H 'Idempotency-Key: e2e-start' >/dev/null; wait_state "$IID" running

step "delete needs confirmation"
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -H 'Idempotency-Key: e2e-del0' -X DELETE "$API/api/v1/instances/$IID")
[ "$code" = 422 ] || fail "delete without confirmation should be 422, got $code"
req -X DELETE "$API/api/v1/instances/$IID?confirm_name=web-e2e" -H 'Idempotency-Key: e2e-del' >/dev/null
for _ in $(seq 1 60); do docker inspect "$C" >/dev/null 2>&1 || break; sleep 2; done
docker inspect "$C" >/dev/null 2>&1 && fail "container still exists after delete"

step "audit chain verifies"
req "$API/api/v1/audit/verify" | jq -e '.valid == true' >/dev/null || fail "audit chain invalid"

step "frontend and security headers"
curl -fsS "$WEB/" | grep -qi '<div id="root">' || fail "frontend not served"
curl -fsSI "$WEB/" | grep -qi 'content-security-policy' || fail "frontend CSP header missing"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB/api/v1/auth/me")" = 401 ] || fail "proxy to API failed"

step "metrics (token protected)"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/metrics")" = 401 ] || fail "/metrics should require a token"
echo "E2E OK"
