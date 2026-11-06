#!/usr/bin/env bash
# Lint the units in deploy/systemd with `systemd-analyze verify`: unknown or misspelt directives,
# bad values, units that name a unit that does not exist, and an ExecStart that cannot run. The
# "systemd units" job in .github/workflows/ci.yml runs it.
#
# The units name files under /opt/data-director/current and a service user that exist only on the
# VM, so the check builds a throwaway root with stand-ins for them and verifies against that
# (`--root`). Run it as any user on a host with systemd 250 or later:
#
#   bash scripts/check_systemd.sh
set -euo pipefail

src=$(cd "$(dirname "$0")/.." && pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

unit_dir=$root/etc/systemd/system
app=$root/opt/data-director/current
mkdir -p "$unit_dir" "$app/deploy" "$app/.venv/bin" "$root/usr/lib/systemd"
# The host's own units (sysinit.target, network-online.target), which ours order themselves after.
system_units=/usr/lib/systemd/system
[ -d "$system_units" ] || system_units=/lib/systemd/system
cp -r "$system_units" "$root/usr/lib/systemd/"
cp -r "$src"/deploy/systemd/. "$unit_dir"/

# Every executable a unit starts, as a stand-in; the agent template's is per instance.
grep -rhoE '^Exec[A-Za-z]*=[-@+!:]*/opt/data-director/current/[^ ]+' "$unit_dir" |
  sed -E 's/^[^=]*=[-@+!:]*//' | sed 's/%i/example-hello/' | sort -u |
  while IFS= read -r exe; do
    mkdir -p "$root$(dirname "$exe")"
    : >"$root$exe"
    chmod +x "$root$exe"
  done

# The service user, so that User= resolves.
mkdir -p "$root/etc"
echo "datadirector:x:900:900::/opt/data-director:/usr/sbin/nologin" >"$root/etc/passwd"
echo "datadirector:x:900:" >"$root/etc/group"

# Plain units, then the template through an instance: verify does not instantiate on its own.
units=()
for f in "$unit_dir"/*.service "$unit_dir"/*.timer "$unit_dir"/*.target "$unit_dir"/*.path; do
  [ -e "$f" ] || continue
  case "$f" in
    *@.service) ;;
    *) units+=("$f") ;;
  esac
done
for f in "$unit_dir"/*@.service; do
  [ -e "$f" ] || continue
  units+=("${f%@.service}@example-hello.service")
  cp "$f" "${f%@.service}@example-hello.service"
done

echo "Verifying ${#units[@]} units"
# Older systemd versions only warn about some problems and still exit 0, so any output fails.
output=$(systemd-analyze verify --root="$root" "${units[@]}" 2>&1) || status=$?
if [ -n "$output" ]; then
  echo "::error::systemd-analyze verify reported problems"
  echo "${output//$root/}"
  exit 1
fi
exit "${status:-0}"
