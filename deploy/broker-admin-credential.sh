#!/usr/bin/env bash
# Give the admin service a credential for the model broker's summary, and the broker its digest
# (docs/guide/operations/model-broker.md, "What the admin service reads"). Run as root from a
# clone of the repository:
#
#   sudo deploy/broker-admin-credential.sh
#
# It makes a random credential and writes it to /etc/data-director/credentials/admin/
# model-broker-admin, and its SHA-256 digest to /etc/data-director/credentials/model-broker/
# admin-credential, each readable by root alone; the broker holds only the digest. It then writes
# both units' drop-ins (sync_broker_admin in deploy/credentials.sh) and restarts both units. A
# second run replaces the credential. `--remove` removes both files and both drop-ins.
#
# DD_ETC and DD_UNIT_DIR replace /etc/data-director and /etc/systemd/system, for its tests; with
# DD_UNIT_DIR set, no unit is restarted.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
ETC="${DD_ETC:-/etc/data-director}"
CREDENTIALS="$ETC/credentials"
UNIT_DIR="${DD_UNIT_DIR:-/etc/systemd/system}"
AGENTS_DIR="$SRC/deploy/agents"
# shellcheck source=deploy/credentials.sh
source "$SRC/deploy/credentials.sh"

die() { echo "$0: $*" >&2; exit 1; }

case "${1:-}" in
  -h | --help) echo "usage: $0 [--remove]"; exit 0 ;;
  "" | --remove) ;;
  *) die "unknown argument '$1' (usage: $0 [--remove])" ;;
esac
if [[ -z "${DD_ETC:-}" && $EUID -ne 0 ]]; then
  die "run as root (sudo)"
fi

held="$CREDENTIALS/admin/model-broker-admin"
digest="$CREDENTIALS/model-broker/admin-credential"

if [[ "${1:-}" == --remove ]]; then
  rm -f "$held" "$digest"
  sync_broker_admin
  echo "removed the admin service's credential for the model broker"
else
  install -d -m 0700 "$CREDENTIALS" "$(dirname "$held")" "$(dirname "$digest")"
  credential="$(openssl rand -hex 32)"
  (umask 077 && printf %s "$credential" >"$held.tmp")
  (umask 077 && printf '%s\n' "$(printf %s "$credential" | sha256sum | awk '{print $1}')" >"$digest.tmp")
  unset credential
  mv -f "$held.tmp" "$held"
  mv -f "$digest.tmp" "$digest"
  sync_broker_admin
fi

if [[ -z "${DD_UNIT_DIR:-}" ]]; then
  systemctl daemon-reload
  systemctl try-restart data-director-model-broker.service data-director-admin.service
fi
