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
req() {
  local out; out=$(mktemp)
  local code; code=$(curl -sS -o "$out" -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" "$@") || { cat "$out" >&2; rm -f "$out"; return 22; }
  if [ "$code" -ge 400 ]; then echo "HTTP $code for: $*  body: $(cat "$out")" >&2; rm -f "$out"; return 22; fi
  cat "$out"; rm -f "$out"
}

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

step "networks: real isolated bridges"
NET=$(req -X POST "$API/api/v1/networks" -H 'Content-Type: application/json' -d '{"name":"net-e2e","cidr":"10.77.0.0/16"}' | jq -r .id)
SA=$(req -X POST "$API/api/v1/networks/$NET/subnets" -H 'Content-Type: application/json' -d '{"name":"sub-a","cidr":"10.77.1.0/24"}' | jq -r .id)
SB=$(req -X POST "$API/api/v1/networks/$NET/subnets" -H 'Content-Type: application/json' -d '{"name":"sub-b","cidr":"10.77.2.0/24"}' | jq -r .id)
docker network inspect "novacloud-net-$SA" >/dev/null || fail "docker network for subnet A missing"
[ "$(docker network inspect -f '{{.Internal}}' "novacloud-net-$SA")" = true ] || fail "subnet network is not internal"
mk() { req -X POST "$API/api/v1/instances" -H 'Content-Type: application/json' -H "Idempotency-Key: e2e-$1" \
  -d "{\"name\":\"$1\",\"template\":\"$2\",\"network_id\":\"$NET\",\"subnet_id\":\"$3\"}" | jq -r .instance.id; }
SRV=$(mk srv-e2e nginx-small "$SA"); CLI=$(mk cli-e2e alpine-small "$SA"); OUT=$(mk out-e2e alpine-small "$SB")
wait_state "$SRV" running; wait_state "$CLI" running; wait_state "$OUT" running
SIP=$(req "$API/api/v1/instances/$SRV" | jq -r .ip)
[ "$SIP" = "10.77.1.2" ] || fail "unexpected server ip $SIP"
for _ in $(seq 1 15); do docker exec "novacloud-$CLI" wget -q -T 3 -O- "http://$SIP:8080" 2>/dev/null | grep -qi nginx && break; sleep 2; done
docker exec "novacloud-$CLI" wget -q -T 3 -O- "http://$SIP:8080" | grep -qi nginx || fail "same-subnet container cannot reach the server"
if docker exec "novacloud-$OUT" wget -q -T 3 -O- "http://$SIP:8080" >/dev/null 2>&1; then fail "other subnet reached the server (no isolation)"; fi
if docker exec "novacloud-$CLI" wget -q -T 3 -O- http://1.1.1.1 >/dev/null 2>&1; then fail "internal network reached the internet"; fi
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -X DELETE "$API/api/v1/networks/$NET/subnets/$SA")
[ "$code" = 409 ] || fail "deleting a subnet with allocated addresses should be 409, got $code"
for pair in "$SRV:srv-e2e" "$CLI:cli-e2e" "$OUT:out-e2e"; do
  id=${pair%%:*}; nm=${pair#*:}
  req -X DELETE "$API/api/v1/instances/$id?confirm_name=$nm" -H "Idempotency-Key: e2e-del-$nm" >/dev/null
done
for id in "$SRV" "$CLI" "$OUT"; do wait_state "$id" deleted; done
del_subnet() { for _ in $(seq 1 15); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -X DELETE "$API/api/v1/networks/$NET/subnets/$1")" = 204 ] && return 0; sleep 1; done
  fail "could not delete subnet $1"; }
del_subnet "$SA"; del_subnet "$SB"
docker network inspect "novacloud-net-$SA" >/dev/null 2>&1 && fail "docker network not removed with subnet"
req -X DELETE "$API/api/v1/networks/$NET" >/dev/null

step "egress policy and published ports"
NET2=$(req -X POST "$API/api/v1/networks" -H 'Content-Type: application/json' -d '{"name":"net-e2e-out","cidr":"10.78.0.0/16"}' | jq -r .id)
SE=$(req -X POST "$API/api/v1/networks/$NET2/subnets" -H 'Content-Type: application/json' -d '{"name":"sub-out","cidr":"10.78.1.0/24","egress":true}' | jq -r .id)
SI=$(req -X POST "$API/api/v1/networks/$NET2/subnets" -H 'Content-Type: application/json' -d '{"name":"sub-in","cidr":"10.78.2.0/24"}' | jq -r .id)
[ "$(docker network inspect -f '{{.Internal}}' "novacloud-net-$SE")" = false ] || fail "egress subnet should not be internal"
[ "$(docker network inspect -f '{{.Internal}}' "novacloud-net-$SI")" = true ] || fail "default subnet should stay internal"
mkp() { curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -X POST "$API/api/v1/instances" -H 'Content-Type: application/json' \
  -H "Idempotency-Key: e2e-$1" -d "{\"name\":\"$1\",\"template\":\"nginx-small\",\"network_id\":\"$NET2\",\"subnet_id\":\"$2\",\"published_port\":$3}"; }
[ "$(mkp pub-bad "$SI" 20081)" -ge 400 ] || fail "publishing on an internal subnet must be refused"
[ "$(mkp pub-e2e "$SE" 20080)" = 202 ] || fail "publishing on an egress subnet should be accepted"
PUB=$(req "$API/api/v1/instances" | jq -r '.[]|select(.name=="pub-e2e").id')
wait_state "$PUB" running
for _ in $(seq 1 15); do curl -fsS http://127.0.0.1:20080 2>/dev/null | grep -qi nginx && break; sleep 2; done
curl -fsS http://127.0.0.1:20080 | grep -qi nginx || fail "published port not reachable on loopback"
[ "$(docker inspect -f '{{(index (index .NetworkSettings.Ports "8080/tcp") 0).HostIp}}' "novacloud-$PUB")" = 127.0.0.1 ] || fail "port not bound to loopback only"
[ "$(mkp pub-dup "$SE" 20080)" = 409 ] || fail "a host port already in use must be refused with 409"
req -X DELETE "$API/api/v1/instances/$PUB?confirm_name=pub-e2e" -H "Idempotency-Key: e2e-del-pub" >/dev/null
wait_state "$PUB" deleted
for sid in "$SE" "$SI"; do for _ in $(seq 1 15); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -X DELETE "$API/api/v1/networks/$NET2/subnets/$sid")" = 204 ] && break; sleep 1; done; done
req -X DELETE "$API/api/v1/networks/$NET2" >/dev/null

step "egress allow-list is enforced"
NET3=$(req -X POST "$API/api/v1/networks" -H 'Content-Type: application/json' -d '{"name":"net-e2e-allow","cidr":"10.79.0.0/16"}' | jq -r .id)
SW=$(req -X POST "$API/api/v1/networks/$NET3/subnets" -H 'Content-Type: application/json' -d '{"name":"sub-allow","cidr":"10.79.1.0/24","egress":true,"egress_allow":["1.1.1.1/32"]}' | jq -r .id)
SF=$(req -X POST "$API/api/v1/networks/$NET3/subnets" -H 'Content-Type: application/json' -d '{"name":"sub-free","cidr":"10.79.2.0/24","egress":true}' | jq -r .id)
code=$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -X POST "$API/api/v1/networks/$NET3/subnets" -H 'Content-Type: application/json' \
  -d '{"name":"sub-bad","cidr":"10.79.3.0/24","egress":true,"egress_allow":["169.254.169.254/32"]}')
[ "$code" -ge 400 ] || fail "metadata address must not be allow-listable"
mka() { req -X POST "$API/api/v1/instances" -H 'Content-Type: application/json' -H "Idempotency-Key: e2e-$1" \
  -d "{\"name\":\"$1\",\"template\":\"alpine-small\",\"network_id\":\"$NET3\",\"subnet_id\":\"$2\"}" | jq -r .instance.id; }
AL=$(mka allow-e2e "$SW"); FR=$(mka free-e2e "$SF")
wait_state "$AL" running; wait_state "$FR" running
reach() { docker exec "novacloud-$1" nc -z -w 4 "$2" 80 >/dev/null 2>&1; }
for _ in $(seq 1 10); do reach "$FR" 1.0.0.1 && break; sleep 2; done
reach "$FR" 1.0.0.1 || fail "egress subnet without allow-list cannot reach the internet"
reach "$AL" 1.1.1.1 || fail "allow-listed destination is unreachable"
if reach "$AL" 1.0.0.1; then fail "destination outside the allow-list was reachable"; fi
for pair in "$AL:allow-e2e" "$FR:free-e2e"; do
  req -X DELETE "$API/api/v1/instances/${pair%%:*}?confirm_name=${pair#*:}" -H "Idempotency-Key: e2e-del-${pair#*:}" >/dev/null
done
wait_state "$AL" deleted; wait_state "$FR" deleted
for sid in "$SW" "$SF"; do for _ in $(seq 1 15); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' -b "$JAR" -H "X-CSRF-Token: $CSRF" -X DELETE "$API/api/v1/networks/$NET3/subnets/$sid")" = 204 ] && break; sleep 1; done; done
req -X DELETE "$API/api/v1/networks/$NET3" >/dev/null
if sudo iptables -S 2>/dev/null | grep -q "NOVA-"; then fail "firewall chain left behind after subnet deletion"; fi

step "audit chain verifies"
req "$API/api/v1/audit/verify" | jq -e '.valid == true' >/dev/null || fail "audit chain invalid"

step "frontend and security headers"
curl -fsS "$WEB/" | grep -qi '<div id="root">' || fail "frontend not served"
curl -fsSI "$WEB/" | grep -qi 'content-security-policy' || fail "frontend CSP header missing"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB/api/v1/auth/me")" = 401 ] || fail "proxy to API failed"

step "metrics (token protected)"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$API/metrics")" = 401 ] || fail "/metrics should require a token"
echo "E2E OK"
