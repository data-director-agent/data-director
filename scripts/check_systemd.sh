#!/usr/bin/env bash
# Lint the units in deploy/systemd twice. `systemd-analyze verify` uses systemd's own parser and
# finds unknown or misspelt directives, bad values, units that name a unit that does not exist, and
# an ExecStart that cannot run. systemdlint (pinned below) adds checks verify lacks, such as
# conflicting options and hardening advice; it has its own, older, idea of what systemd accepts, so
# each finding is compared with deploy/systemd-lint-baseline.txt and only a finding that is not in
# it fails. The "systemd units" job in .github/workflows/ci.yml runs it.
#
# The units name files under /opt/data-director/current and a service user that exist only on the
# VM, so the check builds a throwaway root with stand-ins for them and verifies against that
# (`--root`). Run it as any user on a host with systemd 250 or later and uv installed:
#
#   bash scripts/check_systemd.sh [units-dir [baseline-file]]
set -euo pipefail

systemdlint_version=1.4.0
src=$(cd "$(dirname "$0")/.." && pwd)
units_src=$(cd "${1:-$src/deploy/systemd}" && pwd)
baseline=${2:-$src/deploy/systemd-lint-baseline.txt}
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

unit_dir=$root/etc/systemd/system
app=$root/opt/data-director/current
mkdir -p "$unit_dir" "$app/deploy" "$app/.venv/bin" "$root/usr/lib/systemd"
# The host's own units (sysinit.target, network-online.target), which ours order themselves after.
system_units=/usr/lib/systemd/system
[ -d "$system_units" ] || system_units=/lib/systemd/system
cp -r "$system_units" "$root/usr/lib/systemd/"
cp -r "$units_src"/. "$unit_dir"/

# Every executable a unit starts from the release or from what install.sh installs as root, as a
# stand-in; the agent template's is per instance.
grep -rhoE '^Exec[A-Za-z]*=[-@+!:]*(/opt/data-director/current|/usr/local/lib/data-director)/[^ ]+' "$unit_dir" |
  sed -E 's/^[^=]*=[-@+!:]*//' | sed 's/%i/example-hello/' | sort -u |
  while IFS= read -r exe; do
    mkdir -p "$root$(dirname "$exe")"
    : >"$root$exe"
    chmod +x "$root$exe"
  done

# A host executable a unit starts (systemctl) is not in the throwaway root either, so it gets a
# stand-in too; one the host lacks stays missing and fails.
grep -rhoE '^Exec[A-Za-z]*=[-@+!:]*/[^ ]+' "$unit_dir" | sed -E 's/^[^=]*=[-@+!:]*//' | sort -u |
  while IFS= read -r exe; do
    [ -x "$exe" ] || continue
    mkdir -p "$root$(dirname "$exe")"
    : >"$root$exe"
    chmod +x "$root$exe"
  done

# The service users, so that User= resolves: the deployment's, and the model broker's own.
mkdir -p "$root/etc"
{
  echo "datadirector:x:900:900::/opt/data-director:/usr/sbin/nologin"
  echo "data-director-broker:x:901:901::/var/lib/data-director-model-broker:/usr/sbin/nologin"
} >"$root/etc/passwd"
{
  echo "datadirector:x:900:"
  echo "data-director-broker:x:901:"
} >"$root/etc/group"

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
failed=0

# Older systemd versions only warn about some problems and still exit 0, so any output fails.
# --recursive-errors counts a problem in a unit that a unit names against the unit that names it.
output=$(systemd-analyze verify --recursive-errors=yes --root="$root" "${units[@]}" 2>&1) || true
if [ -n "$output" ]; then
  echo "::error::systemd-analyze verify reported problems"
  echo "${output//$root/}"
  failed=1
fi

# systemdlint reads the units as written (the template, not an instance); --norootfs skips its
# checks of a root filesystem. A finding is keyed "<unit> <rule>", as in the baseline.
if ! command -v uvx >/dev/null; then
  echo "::error::uvx is needed to run systemdlint"
  exit 1
fi
lint_files=()
for f in "$units_src"/*.service "$units_src"/*.timer "$units_src"/*.target "$units_src"/*.path; do
  [ -e "$f" ] && lint_files+=("$f")
done
findings=$(uvx --quiet --from "systemdlint==$systemdlint_version" systemdlint \
  --norootfs "${lint_files[@]}" 2>&1 || true)
found=$(printf '%s\n' "$findings" |
  sed -nE 's#^.*/([^/:]+):[0-9]+:[a-z]+ \[([^]]+)\].*$#\1 \2#p' | sort -u)
known=$(sed -E 's/[[:space:]]*#.*$//; /^[[:space:]]*$/d' "$baseline" | sort -u)
if [ -n "$findings" ] && [ -z "$found" ]; then
  echo "::error::systemdlint printed output this script cannot read"
  echo "$findings"
  failed=1
fi
new=$(comm -23 <(printf '%s\n' "$found") <(printf '%s\n' "$known") | sed '/^$/d')
stale=$(comm -13 <(printf '%s\n' "$found") <(printf '%s\n' "$known") | sed '/^$/d')
if [ -n "$new" ]; then
  echo "::error::systemdlint found problems that are not in $(basename "$baseline")"
  while IFS= read -r key; do
    printf '%s\n' "$findings" | grep -F "/${key%% *}:" | grep -F "[${key#* }]" || true
  done <<<"$new"
  failed=1
fi
if [ -n "$stale" ]; then
  echo "::error::$(basename "$baseline") lists findings systemdlint no longer reports; remove them:"
  echo "$stale"
  failed=1
fi
exit "$failed"
