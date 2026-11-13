# shellcheck shell=bash
# Agents' secrets as systemd credentials (deploy/README.md, "Secrets"). Sourced by
# deploy/install.sh and deploy/secret.sh, so the mapping from file to drop-in is written once.
#
# Each regular file /etc/data-director/credentials/<agent>/<secret> becomes, in
# /etc/systemd/system/data-director-agent@<agent>.service.d/credentials.conf:
#
#   LoadCredential=<secret>:/etc/data-director/credentials/<agent>/<secret>
#   Environment=<SECRET>_FILE=<secret>
#
# where <SECRET> is the name in upper case with underscores (anthropic-api-key ->
# ANTHROPIC_API_KEY_FILE), which dd_sdk.credentials resolves against $CREDENTIALS_DIRECTORY.
# systemd copies the root-only file into that one unit's credentials directory, so no other
# agent can read it although all run as one user. systemd does not start a unit whose credential
# file is missing (243/CREDENTIALS), so a drop-in names only the files that exist and is removed
# with the last of them.
#
# The caller sets:
#   CREDENTIALS  the credentials root, /etc/data-director/credentials
#   UNIT_DIR     where the drop-ins go, /etc/systemd/system
#   AGENTS_DIR   deploy/agents in the release or clone: an agent is deployed if it has <agent>.env
# credentials/app/ is the app's own, loaded by data-director-app.service, and is left alone.

# A secret's name: lower-case words joined by hyphens.
SECRET_NAME='^[a-z0-9]+(-[a-z0-9]+)*$'

# The variable an agent reads a secret's file name from.
credential_variable() { # credential_variable SECRET
  local upper="${1^^}"
  printf '%s_FILE\n' "${upper//-/_}"
}

is_agent() { # is_agent NAME
  [[ "$1" != app && "$1" != model-broker && "$1" =~ ^[a-z0-9-]+$ && -f "$AGENTS_DIR/$1.env" ]]
}

# Why FILE cannot be used as a secret, or nothing if it can.
secret_problem() { # secret_problem FILE
  local name
  name="$(basename "$1")"
  if [[ ! "$name" =~ $SECRET_NAME ]]; then
    echo "$1: a secret's name is lower-case words joined by hyphens"
  elif [[ -L "$1" || ! -f "$1" ]]; then
    echo "$1: not a regular file"
  elif [[ ! -s "$1" ]]; then
    echo "$1: empty"
  elif [[ ! -O "$1" ]]; then
    echo "$1: not owned by $(id -un)"
  fi
}

dropin_path() { # dropin_path AGENT
  printf '%s/data-director-agent@%s.service.d/credentials.conf\n' "$UNIT_DIR" "$1"
}

# Write AGENT's drop-in from its secrets, or remove it if it has none. Reports each secret on
# stdout and each problem on stderr; returns 1 if there was a problem. A secret with a problem is
# left out, so the agent starts without it and says which variable it lacks.
sync_agent_credentials() { # sync_agent_credentials AGENT
  local agent="$1" dir="$CREDENTIALS/$1" dropin file name problem status=0
  local -a lines=()
  dropin="$(dropin_path "$agent")"
  if [[ -d "$dir" ]]; then
    for file in "$dir"/* "$dir"/.[!.]*; do
      [[ -e "$file" || -L "$file" ]] || continue
      name="$(basename "$file")"
      # secret.sh writes through a hidden temporary file.
      [[ "$name" == .tmp.* ]] && continue
      problem="$(secret_problem "$file")"
      if [[ -n "$problem" ]]; then
        echo "$agent: $problem; left out" >&2
        status=1
        continue
      fi
      lines+=("LoadCredential=$name:$file" "Environment=$(credential_variable "$name")=$name")
      echo "$agent: $name in place ($(credential_variable "$name"))"
    done
  fi
  if ((${#lines[@]} == 0)); then
    rm -f "$dropin"
    rmdir "$(dirname "$dropin")" 2>/dev/null || true
    return "$status"
  fi
  install -d -m 0755 "$(dirname "$dropin")"
  {
    echo "# Written by deploy/install.sh and deploy/secret.sh from the files in $dir"
    echo "# (deploy/credentials.sh). Do not edit: it is rewritten from them."
    echo "[Service]"
    printf '%s\n' "${lines[@]}"
  } >"$dropin.tmp"
  chmod 0644 "$dropin.tmp"
  mv -f "$dropin.tmp" "$dropin"
  return "$status"
}

# Every agent's drop-in: those with a credentials directory, and those with a drop-in left from
# a secret since removed. Returns 1 if anything was reported as a problem.
sync_all_credentials() {
  local dir dropin agent status=0
  local -A seen=()
  for dir in "$CREDENTIALS"/*/; do
    [[ -d "$dir" ]] || continue
    agent="$(basename "$dir")"
    [[ "$agent" == app || "$agent" == model-broker ]] && continue
    seen[$agent]=1
    if ! is_agent "$agent"; then
      echo "$CREDENTIALS/$agent: no deployed agent of that name (deploy/agents/$agent.env); its secrets are not loaded" >&2
      status=1
      continue
    fi
    sync_agent_credentials "$agent" || status=1
  done
  for dropin in "$UNIT_DIR"/data-director-agent@*.service.d/credentials.conf; do
    [[ -e "$dropin" ]] || continue
    agent="${dropin#"$UNIT_DIR"/data-director-agent@}"
    agent="${agent%.service.d/credentials.conf}"
    [[ -n "${seen[$agent]:-}" ]] && continue
    rm -f "$dropin"
    rmdir "$(dirname "$dropin")" 2>/dev/null || true
  done
  return "$status"
}
