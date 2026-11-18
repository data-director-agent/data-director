#!/usr/bin/env bash
# Send the model broker's deployment-paid calls through the gateway's test stack, then check that
# the gateway costed them against the broker's key (deploy/llm-gateway/README.md, "With the model
# broker"). Needs the TEST stack and uv, from a clone of the repository:
#
#   docker compose -f compose.yaml -f compose.test.yaml up -d --wait
#   scripts/testing/broker_e2e.sh
set -euo pipefail
GATEWAY_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
REPO="$(cd "$GATEWAY_DIR/../.." && pwd)"
cd "$GATEWAY_DIR"
set -a
# shellcheck source=/dev/null
source .env
set +a
URL=${LITELLM_URL:-http://127.0.0.1:4000}
export LITELLM_URL="$URL"
ADMIN="python3 scripts/admin.py"
RUN=$(date +%s)

# One key for the broker, tagged as the README asks, limited to the test models it calls.
KEY=$($ADMIN key create "model-broker-$RUN" --models 'claude-sonnet-5-5,test-gpt-*,test-gemini-*' \
      --tags "service:model-broker,run:$RUN" | awk '/^key:/{print $2}')
[[ "$KEY" == sk-* ]] || { echo "could not create the broker's key" >&2; exit 1; }

(cd "$REPO" && DD_TEST_GATEWAY="$URL" DD_TEST_GATEWAY_KEY="$KEY" \
  uv run pytest -n0 -m gateway broker/tests/test_broker_gateway.py)

# The gateway writes spend in batches, so wait for it (up to about a minute).
for _ in $(seq 1 24); do
  # shellcheck disable=SC2016 # a sed expression, not the shell's
  spent=$($ADMIN key info "$KEY" | sed -nE 's/.*spent \$([0-9.,]+).*/\1/p' | tr -d ,)
  if python3 -c "import sys; sys.exit(0 if float('${spent:-0}') > 0 else 1)"; then
    echo "PASS  the gateway costed the broker's calls to its key: \$$spent"
    exit 0
  fi
  sleep 5
done
echo "FAIL  no spend recorded against the broker's key" >&2
exit 1
