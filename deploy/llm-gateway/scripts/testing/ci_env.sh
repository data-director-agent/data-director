#!/usr/bin/env bash
# Write a throwaway .env for the gateway's test stack, with fresh secrets and no provider keys, so
# that CI (and anyone without a .env) can run it. An existing .env is left alone.
#
#   scripts/testing/ci_env.sh
#   docker compose -f compose.yaml -f compose.test.yaml up -d --wait
#   scripts/smoke_test.sh
#   scripts/testing/broker_e2e.sh
set -euo pipefail
cd "$(dirname "$0")/../.."

if [[ -e .env ]]; then
  echo ".env exists; leaving it as it is" >&2
  exit 0
fi
secret() { echo "sk-$(openssl rand -hex 32)"; }
umask 077
cat > .env <<ENV
LITELLM_MASTER_KEY=$(secret)
LITELLM_SALT_KEY=$(secret)
POSTGRES_PASSWORD=$(openssl rand -hex 24)
# Use the price list shipped with the image, not one downloaded at start-up.
LITELLM_LOCAL_MODEL_COST_MAP=True
ENV
echo "wrote $(pwd)/.env" >&2
