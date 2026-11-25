#!/usr/bin/env bash
# Restart what data-director.target runs, a few units at a time, instead of all at once. Sixteen
# agents starting together load every module at once on a small VM, with people mid-session
# (#1616). Run as root by data-director-restart.service when deploy.sh asks, and by deploy.sh
# itself when it runs as root. install.sh installs this copy from the clone, so that a commit to
# the branch cannot change what runs as root.
#
#   1. the agents, DD_RESTART_BATCH (default 4) at a time, DD_RESTART_PAUSE seconds (default 5)
#      between batches;
#   2. every other unit the target holds, except the app;
#   3. the app, which waits for the agents' ports at start (wait-for-ports.sh).
#
# `systemctl restart` of a unit returns once it has started, so a batch is started before the
# next, not ready; the pause gives it time to load.
set -euo pipefail

TARGET="${DD_RESTART_TARGET:-data-director.target}"
BATCH="${DD_RESTART_BATCH:-4}"
PAUSE="${DD_RESTART_PAUSE:-5}"
APP="data-director-app.service"

[[ "$BATCH" =~ ^[1-9][0-9]*$ ]] || { echo "error: DD_RESTART_BATCH must be a positive number" >&2; exit 2; }

agents=() others=()
while read -r unit; do
  case "$unit" in
    "") ;;
    "$APP") ;;
    data-director-agent@*.service) agents+=("$unit") ;;
    *.service) others+=("$unit") ;;
  esac
done < <(systemctl list-dependencies --plain --no-legend "$TARGET" | sed 's/^[[:space:]●]*//; s/[[:space:]]*$//')

for ((i = 0; i < ${#agents[@]}; i += BATCH)); do
  ((i > 0)) && sleep "$PAUSE"
  systemctl restart "${agents[@]:i:BATCH}"
done
((${#agents[@]} > 0 && ${#others[@]} > 0)) && sleep "$PAUSE"
((${#others[@]} > 0)) && systemctl restart "${others[@]}"
# The app is started too if the target had stopped it, as `systemctl restart "$TARGET"` would.
systemctl restart "$APP"
