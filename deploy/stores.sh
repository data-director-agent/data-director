# Where a deployment keeps its stores, read from its settings as the units read them
# (deploy/README.md, "Backups"). Sourced by backup.sh and restore.sh, which set STATE.
#
# Three stores: the app's runs and projects, and the workbench's runs. Each is a directory or a
# postgresql:// URL (docs/specs/storage.md). The units set the directory; a setting in app.env or
# workbench.env replaces it.

# shellcheck shell=bash

# shellcheck disable=SC2034 # read by backup.sh and restore.sh, which source this
STORE_NAMES=(runs projects workbench-runs)

# The last value FILE gives NAME, without surrounding quotes; nothing if it gives none.
setting() { # setting FILE NAME
  [[ -r "$1" ]] || return 0
  local value
  value="$(sed -n -E "s/^[[:space:]]*(export[[:space:]]+)?$2=//p" "$1" | tail -n 1)"
  value="${value%"${value##*[![:space:]]}"}"
  if [[ ${#value} -ge 2 && ( "$value" == \"*\" || "$value" == \'*\' ) ]]; then
    value="${value:1:${#value}-2}"
  fi
  printf '%s' "$value"
}

# The settings file a store's location is read from, in the settings directory ETC_DIR.
store_settings() { # store_settings NAME ETC_DIR
  case "$1" in
    workbench-runs) printf '%s' "$2/workbench.env" ;;
    *) printf '%s' "$2/app.env" ;;
  esac
}

# Where store NAME is kept, by the settings in ETC_DIR.
store_location() { # store_location NAME ETC_DIR
  local var default found
  case "$1" in
    runs) var=DD_RUNS_DIR default="$STATE/runs" ;;
    projects) var=DD_PROJECTS_DIR default="$STATE/projects" ;;
    workbench-runs) var=DD_RUNS_DIR default="$STATE/workbench-runs" ;;
    *) return 1 ;;
  esac
  found="$(setting "$(store_settings "$1" "$2")" "$var")"
  printf '%s' "${found:-$default}"
}

is_database() { [[ "$1" == postgresql://* ]]; }

# libpq's settings in FILE (PGHOST, PGPORT, PGPASSFILE, …), one NAME=VALUE a line, for `env`.
libpq_settings() { # libpq_settings FILE
  [[ -r "$1" ]] || return 0
  local name
  sed -n -E 's/^[[:space:]]*(export[[:space:]]+)?(PG[A-Z]+)=.*/\2/p' "$1" | sort -u |
    while IFS= read -r name; do
      printf '%s=%s\n' "$name" "$(setting "$1" "$name")"
    done
}
