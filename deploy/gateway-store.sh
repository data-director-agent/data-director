# The LiteLLM gateway's database in a backup (deploy/README.md, "Backups"): the keys the gateway
# issued, their budgets and its spend. Sourced by backup.sh and restore.sh, which set SYSTEMCTL and
# die, and by restore.sh's `busy` list.
#
# On a VM the gateway runs in Docker under data-director-llm-gateway.service, as the compose
# project data-director-llm-gateway (deploy/llm-gateway/scripts/systemd.sh). Its database is dumped
# and restored inside its own container, so pg_dump and pg_restore always match the server, and the
# containers are found by the labels Docker Compose gives them, not by their names.
#
# DD_DOCKER and DD_GATEWAY_PROJECT replace docker and the project's name, for the tests.

# shellcheck shell=bash

DOCKER="${DD_DOCKER:-docker}"
GATEWAY_PROJECT="${DD_GATEWAY_PROJECT:-data-director-llm-gateway}"
GATEWAY_UNIT=data-director-llm-gateway.service
GATEWAY_DUMP=gateway.pgdump

# The ID of the gateway's running container for compose service SERVICE, or nothing.
gateway_container() { # gateway_container SERVICE
  "$DOCKER" ps -q --filter "label=com.docker.compose.project=$GATEWAY_PROJECT" \
    --filter "label=com.docker.compose.service=$1" 2>/dev/null | head -n 1
}

# Dump the gateway's database into WORK, if the gateway runs, and say so in MANIFEST. A gateway that
# is installed but stopped is noted, not dumped, and the rest of the backup goes on: the doctor
# reports a gateway that does not answer.
gateway_backup() { # gateway_backup WORK MANIFEST
  local db
  if ! "$SYSTEMCTL" is-active --quiet "$GATEWAY_UNIT"; then
    if "$SYSTEMCTL" is-enabled --quiet "$GATEWAY_UNIT" 2>/dev/null; then
      echo "backup.sh: $GATEWAY_UNIT is not running, so its database is not in this backup" >&2
      echo "gateway none" >>"$2"
    fi
    return 0
  fi
  db="$(gateway_container db)"
  [[ -n "$db" ]] || die "$GATEWAY_UNIT is active, but its database's container is not running"
  "$DOCKER" exec "$db" pg_dump -U litellm --format=custom litellm >"$1/$GATEWAY_DUMP" ||
    die "could not dump the LiteLLM gateway's database"
  echo "gateway database litellm $GATEWAY_DUMP" >>"$2"
}

# Before restore.sh changes anything: a backup that holds the gateway's database needs the
# gateway's database running to restore into (install.sh --gateway makes it), and one that already
# has spend is busy. A new gateway has its tables and the broker's key already, so neither counts.
gateway_restore_check() { # gateway_restore_check BACKUP
  [[ -f "$1/$GATEWAY_DUMP" ]] || return 0
  GATEWAY_DB="$(gateway_container db)"
  [[ -n "$GATEWAY_DB" ]] || die "$1 holds the LiteLLM gateway's database, but the gateway is not running; run install.sh with --gateway first (deploy/README.md, \"Restore on a clean VM\")"
  local spend
  spend="$("$DOCKER" exec "$GATEWAY_DB" psql -U litellm -d litellm -qtAX \
    -c 'select count(*) from "LiteLLM_SpendLogs"' 2>/dev/null)" || spend=0
  [[ "$spend" == 0 ]] || busy+=("the LiteLLM gateway's database has $spend requests in its spend logs")
}

# Replace the gateway's database with the backup's, the gateway stopped, and give its role the
# password the restored settings in ETC_DIR hold, which the gateway will connect with. The password
# goes to psql on its input, never on a command line. It starts nothing.
gateway_restore() { # gateway_restore BACKUP ETC_DIR
  [[ -f "$1/$GATEWAY_DUMP" ]] || return 0
  local app password_file password
  app="$(gateway_container litellm)"
  if [[ -n "$app" ]]; then
    "$DOCKER" stop "$app" >/dev/null
    echo "stopped the LiteLLM gateway"
  fi
  "$DOCKER" exec -i "$GATEWAY_DB" pg_restore -U litellm -d litellm --no-owner --exit-on-error \
    --single-transaction --clean --if-exists <"$1/$GATEWAY_DUMP" ||
    die "pg_restore could not restore the LiteLLM gateway's database; it is as it was before"
  password_file="$2/credentials/llm-gateway/postgres-password"
  if [[ -s "$password_file" ]]; then
    password="$(<"$password_file")"
    printf "alter role litellm password '%s';\n" "${password//\'/\'\'}" |
      "$DOCKER" exec -i "$GATEWAY_DB" psql -U litellm -d litellm -qX -v ON_ERROR_STOP=1 >/dev/null ||
      die "could not give the LiteLLM gateway's database the restored password"
  fi
  echo "restored the LiteLLM gateway's database"
}
