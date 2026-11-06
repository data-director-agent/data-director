#!/usr/bin/env bash
# Give an agent a secret, such as its model key, as a systemd credential (deploy/README.md,
# "Secrets"). Run as root from a clone of the repository:
#
#   sudo deploy/secret.sh set orchestrator-model anthropic-api-key   # paste the value, then Enter
#   sudo deploy/secret.sh remove advisor-standards anthropic-api-key
#   sudo deploy/secret.sh list
#
# `set` reads the value from the terminal without showing it, or from a pipe, and stores it in
# /etc/data-director/credentials/<agent>/<secret>, readable by root alone. The agent receives it
# as the file named by <SECRET>_FILE (anthropic-api-key -> ANTHROPIC_API_KEY_FILE). The script
# rewrites the agent's drop-in and restarts the agent if it is running; it starts nothing.
#
# DD_ETC and DD_UNIT_DIR replace /etc/data-director and /etc/systemd/system, for its tests.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
ETC="${DD_ETC:-/etc/data-director}"
CREDENTIALS="$ETC/credentials"
UNIT_DIR="${DD_UNIT_DIR:-/etc/systemd/system}"
AGENTS_DIR="$SRC/deploy/agents"
# shellcheck source=deploy/credentials.sh
source "$SRC/deploy/credentials.sh"

usage() {
  echo "usage: $0 set AGENT SECRET | remove AGENT SECRET | list" >&2
  exit 2
}
die() { echo "$0: $*" >&2; exit 1; }

check_names() { # check_names AGENT SECRET
  is_agent "$1" || die "no deployed agent '$1' (deploy/agents/$1.env); the names are those in app/config/agents.yaml with - for ."
  [[ "$2" =~ $SECRET_NAME ]] || die "'$2': a secret's name is lower-case words joined by hyphens, such as anthropic-api-key"
}

# Rewrite AGENT's drop-in, then restart its unit if it is running.
apply() { # apply AGENT
  local unit="data-director-agent@$1.service" status=0
  sync_agent_credentials "$1" || status=1
  if [[ -z "${DD_UNIT_DIR:-}" ]]; then
    systemctl daemon-reload
    if systemctl is-active --quiet "$unit"; then
      systemctl restart "$unit"
      echo "restarted $unit"
    else
      echo "$unit is not running. /etc/data-director/deployment.yaml says what runs; for the"
      echo "model-backed orchestrator, set 'orchestrator: model' there, then: sudo data-director apply"
    fi
  fi
  return "$status"
}

read_value() {
  local value
  if [[ -t 0 ]]; then
    read -rs -p "Value for $2 of $1 (not shown): " value
    echo >&2
  else
    value="$(cat)"
  fi
  # Leading and trailing whitespace, such as the newline a paste or echo adds, is not part of it.
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  [[ -n "$value" ]] || die "no value given"
  [[ "$value" != *$'\n'* ]] || die "the value has more than one line"
  printf '%s' "$value"
}

cmd_set() { # cmd_set AGENT SECRET
  local agent="$1" secret="$2" dir="$CREDENTIALS/$1" target tmp value
  check_names "$agent" "$secret"
  target="$dir/$secret"
  if [[ -e "$target" || -L "$target" ]] && [[ -L "$target" || ! -f "$target" ]]; then
    die "$target exists and is not a regular file; look at it, remove it, and run this again"
  fi
  value="$(read_value "$agent" "$secret")"
  install -d -m 0700 "$CREDENTIALS" "$dir"
  tmp="$(umask 077 && mktemp "$dir/.tmp.XXXXXX")"
  trap 'rm -f "$tmp"' EXIT
  printf '%s' "$value" >"$tmp"
  mv -fT "$tmp" "$target"
  trap - EXIT
  echo "stored $target ($(stat -c %s "$target") bytes)"
  apply "$agent"
}

cmd_remove() { # cmd_remove AGENT SECRET
  local agent="$1" secret="$2" target
  check_names "$agent" "$secret"
  target="$CREDENTIALS/$agent/$secret"
  [[ -e "$target" || -L "$target" ]] || die "$target does not exist"
  [[ -L "$target" || ! -d "$target" ]] || die "$target is a directory; look at it and remove it by hand"
  rm -f "$target"
  rmdir "$CREDENTIALS/$agent" 2>/dev/null || true
  echo "removed $target"
  apply "$agent"
}

cmd_list() {
  local dir file agent name problem found=0
  for dir in "$CREDENTIALS"/*/; do
    [[ -d "$dir" ]] || continue
    agent="$(basename "$dir")"
    [[ "$agent" == app ]] && continue
    for file in "$dir"*; do
      [[ -e "$file" || -L "$file" ]] || continue
      found=1
      name="$(basename "$file")"
      problem="$(secret_problem "$file")"
      if ! is_agent "$agent"; then
        problem="no deployed agent of that name"
      fi
      if [[ -n "$problem" ]]; then
        printf '%-22s %-24s %s\n' "$agent" "$name" "PROBLEM: ${problem#"$file: "}"
      else
        printf '%-22s %-24s %-30s %s bytes\n' "$agent" "$name" "$(credential_variable "$name")" "$(stat -c %s "$file")"
      fi
    done
  done
  ((found)) || echo "no agent has a secret in $CREDENTIALS"
}

[[ $# -ge 1 ]] || usage
if [[ -z "${DD_ETC:-}" && $EUID -ne 0 ]]; then
  die "run as root (sudo)"
fi
case "$1" in
  set) [[ $# -eq 3 ]] || usage; cmd_set "$2" "$3" ;;
  remove) [[ $# -eq 3 ]] || usage; cmd_remove "$2" "$3" ;;
  list) [[ $# -eq 1 ]] || usage; cmd_list ;;
  *) usage ;;
esac
