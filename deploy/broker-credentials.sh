#!/usr/bin/env bash
# Give each named agent a broker credential and write the model broker's list of their digests
# (docs/guide/operations/model-broker.md, "On a VM"). Run as root from a clone of the repository:
#
#   sudo deploy/broker-credentials.sh advisor-standards advisor-policy orchestrator-model
#
# For each agent it makes a random credential, stores it as the agent's `dd-model-broker-credential`
# secret through deploy/secret.sh (which restarts the agent if it is running), and records the
# credential's SHA-256 digest, under the agent's id (`advisor.standards` for `advisor-standards`),
# in /etc/data-director/credentials/model-broker/agent-credentials, readable by root alone. The
# broker holds only digests. Restart it afterwards to read them.
#
# Every run makes new credentials for the agents named and replaces the whole list, so name every
# agent that calls through the broker each time.
#
# DD_ETC and DD_UNIT_DIR replace /etc/data-director and /etc/systemd/system, for its tests.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
ETC="${DD_ETC:-/etc/data-director}"
DIR="$ETC/credentials/model-broker"
SECRET="dd-model-broker-credential"
AGENTS_DIR="$SRC/deploy/agents"
# shellcheck source=deploy/credentials.sh
source "$SRC/deploy/credentials.sh"

die() { echo "$0: $*" >&2; exit 1; }

[[ $# -ge 1 ]] || { echo "usage: $0 AGENT [AGENT...]" >&2; exit 2; }
if [[ -z "${DD_ETC:-}" && $EUID -ne 0 ]]; then
  die "run as root (sudo)"
fi

agents=()
for agent in "$@"; do
  is_agent "$agent" || die "no deployed agent '$agent' (deploy/agents/$agent.env); the names are those in app/config/agents.yaml"
  for seen in "${agents[@]+"${agents[@]}"}"; do
    [[ "$seen" != "$agent" ]] || die "'$agent' is named twice"
  done
  agents+=("$agent")
done

entries=()
for agent in "${agents[@]}"; do
  credential="$(openssl rand -hex 32)"
  # secret.sh reads the value from the pipe, so it is never on a command line.
  printf %s "$credential" | "$SRC/deploy/secret.sh" set "$agent" "$SECRET" >&2
  digest="$(printf %s "$credential" | sha256sum | awk '{print $1}')"
  unset credential
  # The id the harness signs into a grant has a dot where the unit's name has a hyphen.
  entries+=("$(printf '  "%s": "%s"' "${agent/-/.}" "$digest")")
done

install -d -m 0700 "$ETC/credentials" "$DIR"
tmp="$(umask 077 && mktemp "$DIR/.tmp.XXXXXX")"
trap 'rm -f "$tmp"' EXIT
{
  echo "{"
  last=$((${#entries[@]} - 1))
  for i in "${!entries[@]}"; do
    if ((i < last)); then echo "${entries[$i]},"; else echo "${entries[$i]}"; fi
  done
  echo "}"
} >"$tmp"
mv -f "$tmp" "$DIR/agent-credentials"
trap - EXIT
echo "wrote $DIR/agent-credentials for ${#agents[@]} agent(s)"
if [[ -z "${DD_UNIT_DIR:-}" ]]; then
  echo "Restart the broker to read it: sudo systemctl restart data-director-model-broker.service"
fi
