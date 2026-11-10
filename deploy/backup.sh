#!/usr/bin/env bash
# Back up a Data Director deployment (deploy/README.md, "Backups"). Run as root, by
# data-director-backup.timer every night or by hand:
#
#   sudo data-director backup
#
# It writes one directory, <DD_BACKUP_DIR>/<UTC time>/, holding:
#
#   config.tar.gz        /etc/data-director: the settings and every secret
#   units.tar.gz         the systemd drop-ins (data-director*.d), such as a feedback key's
#   state.tar.gz         /var/lib/data-director/.sign-in and any runs set aside before sign-in
#   store-<name>.tar.gz  each store kept in a directory (runs, projects, workbench-runs)
#   db-<name>.pgdump     each database a store names, by pg_dump's custom format
#   MANIFEST             what was backed up, from where, and the release that ran
#   SHA256SUMS           a checksum of each file, which restore.sh checks first
#
# A store in a directory is copied while the app and the workbench are stopped, since the file
# backends append to their logs as they run; they are started again straight after. A database is
# dumped as it runs. The directory appears under its final name only once complete, and backups
# older than DD_BACKUP_KEEP_DAYS are deleted, the newest always kept.
#
# Settings, from /etc/data-director/backup.env: DD_BACKUP_DIR (/var/backups/data-director) and
# DD_BACKUP_KEEP_DAYS (30). DD_ETC, DD_STATE, DD_ROOT, DD_UNIT_DIR and DD_SYSTEMCTL replace
# /etc/data-director, /var/lib/data-director, /opt/data-director, /etc/systemd/system and
# systemctl, for its tests.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ETC="${DD_ETC:-/etc/data-director}"
STATE="${DD_STATE:-/var/lib/data-director}"
ROOT="${DD_ROOT:-/opt/data-director}"
UNIT_DIR="${DD_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${DD_SYSTEMCTL:-systemctl}"
# shellcheck source=deploy/stores.sh
source "$HERE/stores.sh"

die() { echo "backup.sh: $*" >&2; exit 1; }

[[ -n "${DD_ETC:-}" || $EUID -eq 0 ]] || die "run as root (sudo)"

BACKUP_DIR="${DD_BACKUP_DIR:-$(setting "$ETC/backup.env" DD_BACKUP_DIR)}"
BACKUP_DIR="${BACKUP_DIR:-/var/backups/data-director}"
KEEP_DAYS="${DD_BACKUP_KEEP_DAYS:-$(setting "$ETC/backup.env" DD_BACKUP_KEEP_DAYS)}"
KEEP_DAYS="${KEEP_DAYS:-30}"
[[ "$KEEP_DAYS" =~ ^[1-9][0-9]*$ ]] || die "DD_BACKUP_KEEP_DAYS is '$KEEP_DAYS', not a whole number of days, 1 or more"
[[ "$BACKUP_DIR" == /* ]] || die "DD_BACKUP_DIR is '$BACKUP_DIR', not an absolute path"

# Everything written here is root's alone: the configuration holds every secret.
umask 077
install -d -m 0700 "$BACKUP_DIR"
exec 9>"$BACKUP_DIR/.lock"
flock -n 9 || die "another backup is running"
rm -rf "$BACKUP_DIR"/.partial-*

stamp="$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$BACKUP_DIR/$stamp" ]] || die "$BACKUP_DIR/$stamp exists already; run this again in a second"
work="$BACKUP_DIR/.partial-$stamp"
mkdir -m 0700 "$work"

# The services stopped to copy the file stores; started again however this script ends.
stopped=()
start_again() {
  if ((${#stopped[@]})); then
    "$SYSTEMCTL" start "${stopped[@]}" || echo "backup.sh: could not start ${stopped[*]} again" >&2
    stopped=()
  fi
}
finish() {
  local status=$?
  start_again
  rm -rf "$work"
  exit "$status"
}
trap finish EXIT

manifest="$work/MANIFEST"
{
  echo "format 1"
  echo "created $stamp"
  echo "host $(hostname -f 2>/dev/null || hostname)"
  echo "release $(cat "$ROOT/current/REVISION" 2>/dev/null || echo none)"
} >"$manifest"

[[ -d "$ETC" ]] || die "$ETC does not exist: there is no deployment to back up"
tar -C "$ETC" -czf "$work/config.tar.gz" .

mapfile -t dropins < <(
  [[ -d "$UNIT_DIR" ]] && cd "$UNIT_DIR" &&
    find . -mindepth 1 -maxdepth 1 -type d -name 'data-director*.d' -printf '%P\n' | sort
)
if ((${#dropins[@]})); then
  tar -C "$UNIT_DIR" -czf "$work/units.tar.gz" "${dropins[@]}"
fi

mapfile -t markers < <(
  [[ -d "$STATE" ]] && cd "$STATE" &&
    find . -mindepth 1 -maxdepth 1 \( -name .sign-in -o -name 'runs.before-sign-in-*' \) -printf '%P\n' | sort
)
if ((${#markers[@]})); then
  tar -C "$STATE" -czf "$work/state.tar.gz" "${markers[@]}"
fi

directories=()
databases=()
for name in "${STORE_NAMES[@]}"; do
  location="$(store_location "$name" "$ETC")"
  if is_database "$location"; then
    databases+=("$name")
  else
    [[ "$location" == /* ]] || die "the $name store is '$location', which is not an absolute path"
    [[ -d "$location" ]] || die "the $name store, $location, is not a directory"
    directories+=("$name")
  fi
done

if ((${#directories[@]})); then
  for unit in data-director-app.service data-director-workbench.service; do
    if "$SYSTEMCTL" is-active --quiet "$unit"; then
      stopped+=("$unit")
    fi
  done
  if ((${#stopped[@]})); then
    "$SYSTEMCTL" stop "${stopped[@]}"
  fi
  for name in "${directories[@]}"; do
    location="$(store_location "$name" "$ETC")"
    tar -C "$location" -czf "$work/store-$name.tar.gz" .
    echo "store $name directory $location store-$name.tar.gz" >>"$manifest"
  done
  start_again
fi

declare -A dumped=()
for name in "${databases[@]}"; do
  location="$(store_location "$name" "$ETC")"
  if [[ -n "${dumped[$location]:-}" ]]; then
    echo "store $name database $location ${dumped[$location]}" >>"$manifest"
    continue
  fi
  mapfile -t libpq < <(libpq_settings "$(store_settings "$name" "$ETC")")
  env "${libpq[@]}" pg_dump --format=custom --file="$work/db-$name.pgdump" --dbname="$location" ||
    die "pg_dump could not dump the $name store; pg_dump must be at least the server's major version"
  dumped[$location]="db-$name.pgdump"
  echo "store $name database $location db-$name.pgdump" >>"$manifest"
  harness="$ROOT/current/.venv/bin/dd-harness"
  if [[ -x "$harness" ]]; then
    version="$(env "${libpq[@]}" "$harness" storage status "$location" 2>&1 | tail -n 1)" || true
    echo "schema $name $version" >>"$manifest"
  fi
done

(cd "$work" && sha256sum -- * >SHA256SUMS)
mv -T "$work" "$BACKUP_DIR/$stamp"
echo "backed up to $BACKUP_DIR/$stamp ($(du -sh "$BACKUP_DIR/$stamp" | cut -f1))"

# Retention. A backup's name is its UTC time, so the oldest sort first; the one just written is
# never deleted, whatever the clock says.
cutoff="$(date -u -d "-$KEEP_DAYS days" +%Y%m%dT%H%M%SZ)"
for old in "$BACKUP_DIR"/*; do
  name="$(basename "$old")"
  [[ -d "$old" && "$name" =~ ^[0-9]{8}T[0-9]{6}Z$ && "$name" != "$stamp" ]] || continue
  if [[ "$name" < "$cutoff" ]]; then
    rm -rf "$old"
    echo "deleted $old, older than $KEEP_DAYS days"
  fi
done
