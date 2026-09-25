#!/usr/bin/env bash
# Start every agent service on the port workbench/agents.yaml expects, for local development.
# Ctrl-C stops them all. Then, in another terminal: `uv run workbench serve` (or `invoke`).
set -euo pipefail

cd "$(dirname "$0")/.."

declare -A PORTS=(
  [dd-hello]=8101
  [dd-quality]=8102
  [dd-factcheck]=8103
  [dd-stub]=8104
  [dd-r3]=8105
  [dd-director]=8106
)

pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true' EXIT INT TERM

for script in "${!PORTS[@]}"; do
  port="${PORTS[$script]}"
  echo "starting $script on http://127.0.0.1:$port"
  uv run "$script" serve --port "$port" &
  pids+=("$!")
done

wait
