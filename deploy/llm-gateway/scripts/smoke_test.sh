#!/usr/bin/env bash
# End-to-end check of spend tracking, tags, reports and budget enforcement.
# Needs the TEST stack (fake provider, no real keys, nothing billed):
#   docker compose -f compose.yaml -f compose.test.yaml up -d
#   scripts/smoke_test.sh
#
# Every call uses max_tokens=50 and costs exactly $0.20 (see config.test.yaml).
# Behaviour observed with LiteLLM v1.109.0 (single instance, no Redis), asserted below:
# before each request, key/user/team budgets are compared with the spend recorded
# so far. The request that crosses a limit is still allowed; later ones are refused.
# So a budget can be exceeded by up to one request (more with concurrent requests).
set -uo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
URL=${LITELLM_URL:-http://localhost:4000}
ADMIN="python3 scripts/admin.py"
RUN=$(date +%s)
PASS=0; FAIL=0
BODY=$(mktemp); trap 'rm -f "$BODY"' EXIT
ok()   { echo "  PASS  $*"; PASS=$((PASS+1)); }
bad()  { echo "  FAIL  $*"; FAIL=$((FAIL+1)); }
check(){ local desc=$1 want=$2 got=$3
  if [[ "$got" == "$want" ]]; then ok "$desc"
  else bad "$desc (wanted $want, got $got)"; [[ -s $BODY ]] && echo "        last response: $(head -c 300 "$BODY")"; fi; }
rejected(){ [[ $1 == 400 || $1 == 422 || $1 == 429 ]] && grep -q budget_exceeded "$BODY" && echo yes || echo "no ($1)"; }

openai_call() {  # key, tag -> HTTP status
  sleep 1   # let the previous call's reservation settle
  curl -s -o "$BODY" -w '%{http_code}' "$URL/v1/chat/completions" \
    -H "Authorization: Bearer $1" -H 'Content-Type: application/json' \
    -d "{\"model\":\"test-gpt\",\"max_tokens\":50,\"messages\":[{\"role\":\"user\",\"content\":\"hi\"}],\"metadata\":{\"tags\":[\"$2\"]}}"
}
anthropic_call() {  # key -> HTTP status
  sleep 1
  curl -s -o "$BODY" -w '%{http_code}' "$URL/v1/messages" \
    -H "x-api-key: $1" -H 'anthropic-version: 2023-06-01' -H 'Content-Type: application/json' \
    -d '{"model":"test-claude","max_tokens":50,"messages":[{"role":"user","content":"hi"}]}'
}
money(){ sed -E 's/.*spent \$([0-9.,]+).*/\1/' | tr -d ,; }

echo "1. Gateway is up"
check "liveliness endpoint" 200 "$(curl -s -o /dev/null -w '%{http_code}' "$URL/health/liveliness")"
check "admin UI responds"   200 "$(curl -s -o /dev/null -L -w '%{http_code}' "$URL/ui/")"

echo "2. Create team (budget \$1.00), user and key (budget \$0.50)"
TEAM=$($ADMIN team create "smoke-team-$RUN" --budget 1.0 --period 30d | awk '/team_id/{print $2}')
[[ -n "$TEAM" ]] && ok "team created" || bad "team create"
USERID=$($ADMIN user create "smoke-$RUN@example.ac.uk" --team "$TEAM" | awk '/user_id/{print $2}')
[[ -n "$USERID" ]] && ok "user created" || bad "user create"
KEY=$($ADMIN key create "smoke-key-$RUN" --team "$TEAM" --user "$USERID" --budget 0.5 \
      --tags "project:smoke-$RUN" | awk '/^key:/{print $2}')
[[ "$KEY" == sk-* ]] && ok "key created" || bad "key create"

echo "3. Both API styles, then the key budget (\$0.50) is enforced"
check "call via OpenAI route allowed"    200 "$(openai_call "$KEY" "exp:a-$RUN")"
check "call via Anthropic route allowed" 200 "$(anthropic_call "$KEY")"
K_OK=2; K_REFUSED=no
for n in $(seq 1 8); do
  s=$(openai_call "$KEY" "exp:a-$RUN")
  if [[ $s == 200 ]]; then K_OK=$((K_OK+1)); else K_REFUSED=$(rejected "$s"); break; fi
done
check "key eventually refused with budget_exceeded" yes "$K_REFUSED"
echo "        key calls allowed: $K_OK"

echo "4. The team budget (\$1.00) caps every key in the team"
KEY2=$($ADMIN key create "smoke-key2-$RUN" --team "$TEAM" --tags "project:smoke-$RUN" | awk '/^key:/{print $2}')
T_OK=0; T_REFUSED=no
for n in $(seq 1 8); do
  s=$(openai_call "$KEY2" "exp:b-$RUN")
  if [[ $s == 200 ]]; then T_OK=$((T_OK+1)); else T_REFUSED=$(rejected "$s"); break; fi
done
check "second key refused with budget_exceeded" yes "$T_REFUSED"
grep -q "Team=" "$BODY" && ok "refusal names the team budget" || bad "refusal does not mention the team"
echo "        second-key calls allowed: $T_OK"

dollars(){ python3 -c "print(f'{$1*0.20:.2f}')"; }
echo "5. Spend persisted to the database (batched writes, can take up to ~60s)"
WANT_K=$(dollars $K_OK); WANT_T=$(dollars $((K_OK+T_OK)))
for i in $(seq 1 24); do
  kspent=$(printf '%.2f' "$($ADMIN key info "$KEY" | money)"); tspent=$(printf '%.2f' "$($ADMIN team info "$TEAM" | money)")
  [[ $kspent == "$WANT_K" && $tspent == "$WANT_T" ]] && break; sleep 5
done
check "key spend matches calls made" "$WANT_K" "$kspent"
check "team spend matches calls made" "$WANT_T" "$tspent"
python3 -c "import sys; sys.exit(0 if $tspent <= 1.0 + 0.20 + 1e-9 else 1)" \
  && ok "team spend \$$tspent within \$1.00 budget plus at most one request" || bad "team overspent: \$$tspent"
python3 -c "import sys; sys.exit(0 if $kspent <= 0.5 + 0.20 + 1e-9 else 1)" \
  && ok "key spend \$$kspent within \$0.50 budget plus at most one request" || bad "key overspent: \$$kspent"

echo "6. Reports from the request logs"
for i in $(seq 1 12); do
  report=$($ADMIN spend --by tag)
  grep -qE "^project:smoke-$RUN .* $WANT_T" <<<"$report" && break; sleep 5
done
grep -E "^tag|-$RUN " <<<"$report" | sed 's/^/        /'
row() { grep -E "^$1 " <<<"$report" | awk '{printf "%.2f", $NF}'; }
check "tag project:smoke (from key metadata) = all team spend" "$WANT_T" "$(row "project:smoke-$RUN")"
check "tag exp:a (per-request tag)" "$(dollars $((K_OK-1)))" "$(row "exp:a-$RUN")"
check "tag exp:b (per-request tag)" "$(dollars $T_OK)" "$(row "exp:b-$RUN")"
CSV=$(mktemp --suffix .csv)
$ADMIN export --team "$TEAM" --out "$CSV" >/dev/null
check "CSV export has one row per successful team call" "$((K_OK+T_OK))" \
  "$(python3 -c "import csv;print(sum(1 for r in csv.DictReader(open('$CSV')) if r['status']=='success'))")"
rm -f "$CSV"

echo "7. Prometheus metrics"
METRICS=$(curl -s "$URL/metrics/" -H "Authorization: Bearer $LITELLM_MASTER_KEY")
grep -q "^litellm_spend_metric_total{.*team_alias=\"smoke-team-$RUN\"" <<<"$METRICS" \
  && ok "litellm_spend_metric_total exported with team label" || bad "spend metric missing"

echo; echo "Passed: $PASS   Failed: $FAIL"
[[ $FAIL -eq 0 ]]
