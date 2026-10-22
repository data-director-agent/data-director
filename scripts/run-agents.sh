#!/usr/bin/env bash
# Start every agent service on the port workbench/agents.yaml expects, for local development.
# Ctrl-C stops them all. Then, in another terminal: `uv run workbench serve` (or `invoke`).
set -euo pipefail

cd "$(dirname "$0")/.."

declare -A PORTS=(
  [dd-hello]=8101
  [dd-quality]=8102
  [dd-standards]=8105
  [dd-director]=8106
  [dd-orchestrator]=8107
)

# Each agent reads the file the workbench loads, if it exists, and then its own,
# workbench/agents/<name>.env (dd-standards: standards.env), whose settings win. A model key goes
# only in the agent's own file, so no other agent is given it (ADR-0026). dd-orchestrator needs
# one (workbench/agents/orchestrator.env); without it, it stops at start-up and the rest run on.
shared=()
[[ -f workbench/.env ]] && shared=(--env-file workbench/.env)

pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM

for script in "${!PORTS[@]}"; do
  port="${PORTS[$script]}"
  env_files=("${shared[@]}")
  own="workbench/agents/${script#dd-}.env"
  [[ -f "$own" ]] && env_files+=(--env-file "$own")
  echo "starting $script on http://127.0.0.1:$port"
  uv run "${env_files[@]}" "$script" serve --port "$port" &
  pids+=("$!")
done

wait
