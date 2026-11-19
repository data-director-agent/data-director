#!/usr/bin/env bash
# Run a command, trying again when it fails: for CI steps that download (browsers, images,
# packages), where a failure is usually the network, not the change.
#   scripts/retry.sh [-n ATTEMPTS] COMMAND [ARGUMENT…]
# Waits 10 s, then 20 s, between attempts, and exits with the last attempt's status.
set -uo pipefail

attempts=3
if [[ "${1:-}" == "-n" ]]; then
  attempts="${2:?-n needs a number}"
  shift 2
fi
(($# > 0)) || {
  echo "usage: retry.sh [-n ATTEMPTS] COMMAND [ARGUMENT…]" >&2
  exit 2
}

for ((i = 1; ; i++)); do
  "$@" && exit 0
  status=$?
  if ((i >= attempts)); then
    echo "retry: '$1' failed $attempts times; giving up" >&2
    exit "$status"
  fi
  delay=$((i * 10))
  echo "retry: '$1' failed (attempt $i of $attempts, exit $status); trying again in ${delay}s" >&2
  sleep "$delay"
done
