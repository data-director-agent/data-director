#!/usr/bin/env bash
# Restore a Data Director deployment from a backup that backup.sh made (deploy/README.md,
# "Restore on a clean VM"). Run as root, after install.sh has made the service user:
#
#   sudo data-director restore /var/backups/data-director/20261110T024300Z
#   sudo data-director restore --force BACKUP     # over stores that already hold something
#
# It checks every file against SHA256SUMS before it changes anything, then stops the services and
# puts back /etc/data-director, the systemd drop-ins, the sign-in marker and each store, where the
# restored settings say it is kept. It refuses a store that already holds something unless given
# --force: a directory is then moved aside to <store>.before-restore-<time>, and a database's
# tables are dropped and replaced. A database must exist; restore.sh fills it and creates none.
# It starts nothing: install.sh, run next, deploys a release if there is none and starts it all.
#
# DD_ETC, DD_STATE, DD_UNIT_DIR and DD_SYSTEMCTL replace /etc/data-director,
# /var/lib/data-director, /etc/systemd/system and systemctl, for its tests.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ETC="${DD_ETC:-/etc/data-director}"
STATE="${DD_STATE:-/var/lib/data-director}"
UNIT_DIR="${DD_UNIT_DIR:-/etc/systemd/system}"
SYSTEMCTL="${DD_SYSTEMCTL:-systemctl}"
USER_NAME=datadirector
# shellcheck source=deploy/stores.sh
source "$HERE/stores.sh"

die() { echo "restore.sh: $*" >&2; exit 1; }
usage() { echo "usage: $0 [--force] BACKUP" >&2; exit 2; }

force=0
backup=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force) force=1; shift ;;
    -*) usage ;;
    *) [[ -z "$backup" ]] || usage; backup="$1"; shift ;;
  esac
done
[[ -n "$backup" ]] || usage
[[ -n "${DD_ETC:-}" || $EUID -eq 0 ]] || die "run as root (sudo)"

# --- Check the backup before anything changes. --------------------------------------------------
[[ -d "$backup" ]] || die "$backup is not a directory"
backup="$(cd "$backup" && pwd)"
for file in MANIFEST SHA256SUMS config.tar.gz; do
  [[ -f "$backup/$file" ]] || die "$backup has no $file: it is not a backup, or not a whole one"
done
grep -qx 'format 1' "$backup/MANIFEST" || die "$backup was made by another version of backup.sh"
(cd "$backup" && sha256sum --quiet --strict -c SHA256SUMS) ||
  die "$backup does not match its checksums; it is damaged, and nothing was changed"
for file in "$backup"/*; do
  name="$(basename "$file")"
  [[ "$name" == SHA256SUMS ]] && continue
  grep -qE "^[0-9a-f]{64} [ *]$name\$" "$backup/SHA256SUMS" ||
    die "$name is in $backup but not in its checksums; nothing was changed"
done

# What the manifest says of store NAME: "<kind> <location> <file>".
recorded() { sed -n "s/^store $1 //p" "$backup/MANIFEST"; }

# What restore.sh makes for itself is root's alone; what it extracts keeps the modes it was backed up
# with (tar -p), as it does by default for root.
umask 077
staged="$(mktemp -d)"
trap 'rm -rf "$staged"' EXIT
install -d -m 0750 "$staged/etc"
tar -C "$staged/etc" -xzpf "$backup/config.tar.gz"

# Each store's place comes from the restored settings, and must be the kind the backup holds.
busy=()
for name in "${STORE_NAMES[@]}"; do
  read -r kind _ file <<<"$(recorded "$name")"
  [[ -n "${file:-}" ]] || die "$backup records nothing of the $name store"
  location="$(store_location "$name" "$staged/etc")"
  if is_database "$location"; then
    [[ "$kind" == database ]] || die "the settings put the $name store in a database, but $backup holds it as a $kind"
    mapfile -t libpq < <(libpq_settings "$(store_settings "$name" "$staged/etc")")
    tables="$(env "${libpq[@]}" psql --no-psqlrc -qtAX --dbname="$location" -c \
      "select count(*) from pg_tables where schemaname not in ('pg_catalog', 'information_schema')")" ||
      die "cannot reach the $name store's database; it must exist (deploy/README.md, \"Restore on a clean VM\")"
    [[ "$tables" == 0 ]] || busy+=("$location (the $name store) has $tables tables")
  else
    [[ "$kind" == directory ]] || die "the settings put the $name store in a directory, but $backup holds it as a $kind"
    [[ "$location" == /* ]] || die "the $name store is '$location', which is not an absolute path"
    if [[ -d "$location" && -n "$(ls -A "$location")" ]]; then
      busy+=("$location (the $name store) is not empty")
    fi
  fi
done
if ((${#busy[@]})) && ((!force)); then
  printf '%s\n' "restore.sh: these already hold something, and nothing was changed:" "${busy[@]/#/  }" >&2
  echo "Run again with --force to set the directories aside and replace the databases' tables." >&2
  exit 1
fi

# --- Restore. -----------------------------------------------------------------------------------
"$SYSTEMCTL" stop data-director.target data-director-workbench.service 2>/dev/null || true

install -d -m 0750 "$ETC"
tar -C "$ETC" -xzpf "$backup/config.tar.gz"
echo "restored $ETC"
if [[ -f "$backup/units.tar.gz" ]]; then
  install -d -m 0755 "$UNIT_DIR"
  tar -C "$UNIT_DIR" -xzpf "$backup/units.tar.gz"
  echo "restored the systemd drop-ins in $UNIT_DIR"
fi
owner=()
if [[ $EUID -eq 0 ]] && id "$USER_NAME" &>/dev/null; then
  owner=(-o "$USER_NAME" -g "$USER_NAME")
fi
install -d "${owner[@]}" -m 0750 "$STATE"
if [[ -f "$backup/state.tar.gz" ]]; then
  tar -C "$STATE" -xzpf "$backup/state.tar.gz"
fi

when="$(date -u +%Y%m%dT%H%M%SZ)"
declare -A done_dumps=()
for name in "${STORE_NAMES[@]}"; do
  read -r kind _ file <<<"$(recorded "$name")"
  location="$(store_location "$name" "$staged/etc")"
  if [[ "$kind" == directory ]]; then
    if [[ -d "$location" && -n "$(ls -A "$location")" ]]; then
      mv -T "$location" "$location.before-restore-$when"
      echo "moved what was in $location to $location.before-restore-$when"
    fi
    install -d "${owner[@]}" -m 0750 "$location"
    tar -C "$location" -xzpf "$backup/$file"
    if ((${#owner[@]})); then
      chown -R "$USER_NAME:$USER_NAME" "$location"
    fi
    echo "restored the $name store to $location"
  else
    if [[ -z "${done_dumps[$file]:-}" ]]; then
      mapfile -t libpq < <(libpq_settings "$(store_settings "$name" "$staged/etc")")
      clean=()
      ((force)) && clean=(--clean --if-exists)
      env "${libpq[@]}" pg_restore --no-owner --exit-on-error --single-transaction "${clean[@]}" \
        --dbname="$location" "$backup/$file" ||
        die "pg_restore could not restore the $name store; its database is as it was before"
      done_dumps[$file]=1
    fi
    echo "restored the $name store to $location"
  fi
done

if [[ -z "${DD_UNIT_DIR:-}" ]]; then
  "$SYSTEMCTL" daemon-reload || true
fi

url="$(setting "$ETC/app.env" DD_APP_PUBLIC_URL)"
domain="${url#https://}"
domain="${domain%%[:/]*}"
echo
echo "Restored $backup, made $(sed -n 's/^created //p' "$backup/MANIFEST") on $(sed -n 's/^host //p' "$backup/MANIFEST")."
echo "Nothing is started yet. To start it all, run from the clone:"
echo "  sudo deploy/install.sh --domain ${domain:-<name>}"
echo "  sudo data-director doctor"
