#!/usr/bin/env bash
# Samples each container's CPU and memory every INTERVAL seconds (default 5) into a CSV, until
# stopped, so resource use can be read next to Locust's results (README.md).
# Usage: loadtest/collect.sh [out.csv]
set -euo pipefail
out="${1:-loadtest/out/containers.csv}"
interval="${INTERVAL:-5}"
mkdir -p "$(dirname "$out")"
echo "time,container,cpu_percent,mem_usage,mem_percent,net_io,block_io,pids" > "$out"
while true; do
  now="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  docker stats --no-stream \
    --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}},{{.NetIO}},{{.BlockIO}},{{.PIDs}}" \
    | sed "s|^|$now,|" >> "$out"
  sleep "$interval"
done
