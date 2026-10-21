#!/usr/bin/env bash
# Wait until every given port on 127.0.0.1 accepts a connection, or give up after a number of
# seconds. The app reads each agent's card once at start-up and lists an agent it cannot reach
# as unavailable, so data-director-app.service runs this first.
#
#   wait-for-ports.sh SECONDS PORT...
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 SECONDS PORT..." >&2
  exit 2
fi

deadline=$((SECONDS + $1))
shift

for port in "$@"; do
  until (exec 3<>"/dev/tcp/127.0.0.1/$port") 2>/dev/null; do
    if ((SECONDS >= deadline)); then
      # Start anyway: the app lists the agent as unavailable and still runs the rest.
      echo "port $port is not answering; the app will list that agent as unavailable" >&2
      exit 0
    fi
    sleep 1
  done
done
