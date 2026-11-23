#!/usr/bin/env bash
# Start or stop the LiteLLM gateway on a VM, for data-director-llm-gateway.service (deploy/README.md,
# "The LiteLLM gateway"). install.sh copies it, with compose.yaml, config.yaml and
# dd_token_guard.py, to /usr/local/lib/data-director/llm-gateway/, and the unit runs that copy as
# root:
#
#   systemd.sh up     start the gateway and its database, and wait until the gateway answers
#   systemd.sh down   stop them; the database's volume, with its keys, budgets and spend, stays
#
# Docker runs what compose.yaml says as root, so the copy is root's, from the clone, never from a
# release: a commit to the branch cannot change it, as with the units. Running install.sh again is
# how a change to it reaches the VM.
#
# The settings are in /etc/data-director/llm-gateway.env. Each secret is a root-only file in
# /etc/data-director/credentials/llm-gateway/, passed in the environment under its name in upper
# case with underscores (anthropic-api-key -> ANTHROPIC_API_KEY). The models are
# /etc/data-director/llm-gateway.yaml if the operator has written one, or config.yaml beside this.
#
# DD_ETC replaces /etc/data-director, for tests.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ETC="${DD_ETC:-/etc/data-director}"
CREDENTIALS="$ETC/credentials/llm-gateway"
# One name whatever directory compose.yaml is in, so that the database's volume is always the same.
PROJECT=data-director-llm-gateway

load() {
  local file name upper
  if [[ -f "$ETC/llm-gateway.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$ETC/llm-gateway.env"
    set +a
  fi
  for file in "$CREDENTIALS"/*; do
    [[ -f "$file" && -s "$file" ]] || continue
    name="$(basename "$file")"
    [[ "$name" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]] || continue
    upper="${name^^}"
    export "${upper//-/_}=$(<"$file")"
  done
  if [[ -f "$ETC/llm-gateway.yaml" ]]; then
    export DD_GATEWAY_CONFIG="$ETC/llm-gateway.yaml"
  fi
}

compose() {
  docker compose --project-name "$PROJECT" --project-directory "$HERE" -f "$HERE/compose.yaml" "$@"
}

case "${1:-}" in
  up)
    load
    # compose.yaml bind-mounts this file. If it is missing Docker makes a directory in its place,
    # and LiteLLM then fails at start with an error that does not say why.
    if [[ ! -f "$HERE/dd_token_guard.py" ]]; then
      echo "$HERE/dd_token_guard.py is missing or not a file: run deploy/install.sh again," \
        "and remove it first if it is a directory" >&2
      exit 1
    fi
    compose up --detach --wait --wait-timeout 300 litellm db
    ;;
  down)
    load
    compose down
    ;;
  *)
    echo "usage: $0 up|down" >&2
    exit 2
    ;;
esac
