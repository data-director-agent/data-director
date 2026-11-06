#!/usr/bin/env bash
# One pass of the deployment (deploy/README.md). Run by data-director-deploy.service as the
# datadirector user, every five minutes:
#
#   1. fetch the branch into the bare clone;
#   2. stop if its tip is already running, failed here before, or has not passed CI;
#   3. build the tip into its own release directory (uv sync, npm build of app/web);
#   4. point /opt/data-director/current at it and restart data-director.target;
#   5. if the app does not report the new commit, point `current` back and restart again.
#
# "Running" means the app reports the commit on /api/about, not only that `current` points at
# it: if the restart failed, the old processes are still serving the old commit.
#
# Settings, each with its default (set them in /etc/data-director/deploy.env):
#   DD_DEPLOY_REPO        https://github.com/data-director-agent/data-director.git
#   DD_DEPLOY_BRANCH      main
#   DD_DEPLOY_CHECK       CI passed       the check run that must have succeeded on the commit
#   DD_DEPLOY_ROOT        /opt/data-director
#   DD_DEPLOY_KEEP        3               release directories kept, the live one included
#   DD_DEPLOY_ABOUT_URL   http://127.0.0.1:7860/api/about   where the app names its commit
#   GITHUB_TOKEN          (unset)         only for a private repository or the API rate limit
#
# `deploy.sh --force` skips the CI check and the record of failed commits.
set -euo pipefail

REPO="${DD_DEPLOY_REPO:-https://github.com/data-director-agent/data-director.git}"
BRANCH="${DD_DEPLOY_BRANCH:-main}"
CHECK="${DD_DEPLOY_CHECK:-CI passed}"
ROOT="${DD_DEPLOY_ROOT:-/opt/data-director}"
KEEP="${DD_DEPLOY_KEEP:-3}"
# /api/about answers without a session, so the check works with sign-in on (app/README.md).
ABOUT_URL="${DD_DEPLOY_ABOUT_URL:-http://127.0.0.1:7860/api/about}"
# Seconds the app has to report the new commit after a restart: the agents get 60 (wait-for-ports.sh) and the
# app then reads their cards.
HEALTH_TIMEOUT=120

FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

BARE="$ROOT/repo.git"
RELEASES="$ROOT/releases"
CURRENT="$ROOT/current"
FAILED="$ROOT/failed-commits"

log() { echo "$*"; }
die() { echo "error: $*" >&2; exit 1; }

# The commit the running app reports, or nothing if it does not answer.
running_commit() {
  curl --fail --silent --max-time 5 "$ABOUT_URL" 2>/dev/null | jq -r '.commit // empty' 2>/dev/null || true
}

# Restart the app and agents. install.sh allows this one command in /etc/sudoers.d/data-director;
# without that rule sudo asks for a password, and nothing is restarted.
restart() {
  # Without the lock's descriptor, so that nothing started here can hold the lock.
  sudo --non-interactive /usr/bin/systemctl restart data-director.target 9>&- ||
    die "could not restart data-director.target; is /etc/sudoers.d/data-director in place? (deploy/README.md)"
}

link() {
  ln -sfn "$1" "$ROOT/current.new"
  mv -T "$ROOT/current.new" "$CURRENT"
}

# Wait until the app reports the given commit.
healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT))
  until [[ "$(running_commit)" == "$1" ]]; do
    ((SECONDS >= deadline)) && return 1
    sleep 2
  done
}

# One pass at a time, whether from the timer or by hand.
exec 9>"$ROOT/deploy.lock"
flock -n 9 || { log "another deployment is running"; exit 0; }

# --- 1. Fetch ----------------------------------------------------------------------------------

if [[ ! -d "$BARE" ]]; then
  git clone --quiet --bare --single-branch --branch "$BRANCH" "$REPO" "$BARE"
fi
git -C "$BARE" fetch --quiet --force "$REPO" "+refs/heads/$BRANCH:refs/heads/$BRANCH"
sha="$(git -C "$BARE" rev-parse "refs/heads/$BRANCH")"
short="${sha:0:12}"

# --- 2. Decide ---------------------------------------------------------------------------------

live=""
[[ -L "$CURRENT" ]] && live="$(basename "$(readlink "$CURRENT")")"
if [[ "$live" == "$sha" ]]; then
  # Linked but not running: an earlier pass switched the link and then could not restart.
  running="$(running_commit)"
  if [[ -n "$running" && "$running" != "$sha" ]]; then
    log "$short: is current but the app reports ${running:0:12}; restarting"
    restart
    healthy "$sha" || die "$short: the app did not report $short at $ABOUT_URL after a restart"
    log "$short: live"
  fi
  exit 0
fi

if ((FORCE == 0)); then
  if [[ -f "$FAILED" ]] && grep -qx "$sha" "$FAILED"; then
    exit 0
  fi

  # The check runs on the commit. The repository is public, so no token is needed; 60
  # unauthenticated requests an hour is more than one every five minutes uses.
  slug="$(sed -E 's#^(https://github.com/|ssh://git@github.com/|git@github.com:)##; s#\.git$##' <<<"$REPO")"
  auth=()
  [[ -n "${GITHUB_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer $GITHUB_TOKEN")
  conclusion="$(
    curl --fail --silent --show-error --max-time 30 "${auth[@]}" \
      -H "Accept: application/vnd.github+json" \
      --get --data-urlencode "check_name=$CHECK" \
      "https://api.github.com/repos/$slug/commits/$sha/check-runs" |
      jq -r '[.check_runs[] | .conclusion // .status] | if length == 0 then "missing" else (if any(. == "success") then "success" else .[0] end) end'
  )" || die "could not read the checks on $short from GitHub"

  case "$conclusion" in
    success) ;;
    missing | queued | in_progress | pending | waiting | requested)
      log "$short: \"$CHECK\" has not finished; waiting"
      exit 0
      ;;
    *)
      # Not recorded as failed: if CI is re-run and passes, the commit is deployed then.
      log "$short: \"$CHECK\" ended $conclusion; not deploying it"
      exit 0
      ;;
  esac
fi

# --- 3. Build ----------------------------------------------------------------------------------

# A release is built where it will run: dd_app finds app/config and app/web/dist beside its own
# source, and the virtual environment records its own path, so neither can be moved afterwards.
release="$RELEASES/$sha"
if [[ ! -f "$release/.built" ]]; then
  log "$short: building"
  rm -rf "$release"
  mkdir -p "$release"
  git -C "$BARE" archive "$sha" | tar -x -C "$release"
  # A release has no .git, so the app reads the commit it was built from here (dd_app.about).
  echo "$sha" >"$release/REVISION"
  # Chained with &&: on the left of `||`, bash ignores `set -e`, so each step must stop the next.
  # Only dist is served; the packages are hundreds of megabytes per release.
  (
    cd "$release" &&
      uv sync --locked --no-dev --quiet &&
      cd app/web &&
      npm ci --no-audit --no-fund --loglevel=error &&
      npm run build --silent &&
      rm -rf node_modules
  ) || die "$short: build failed"
  echo "$sha" >"$release/.built"
fi

# --- 4. Switch ---------------------------------------------------------------------------------

previous=""
[[ -L "$CURRENT" ]] && previous="$(readlink -f "$CURRENT")"

was="${live:0:12}"
log "$short: going live (was ${was:-nothing})"
link "$release"
# A failed restart leaves the old processes running: put the link back so that the next pass
# tries again, instead of taking the link for the running release.
if ! (restart); then
  [[ -n "$previous" ]] && link "$previous"
  exit 1
fi

# --- 5. Check, or roll back --------------------------------------------------------------------

if ! healthy "$sha"; then
  echo "$sha" >>"$FAILED"
  if [[ -n "$previous" ]]; then
    log "$short: the app did not report $short at $ABOUT_URL; rolling back to ${live:0:12}"
    link "$previous"
    restart
    healthy "$live" || die "${live:0:12} did not answer after the rollback either"
  fi
  die "$short: the app did not report $short at $ABOUT_URL"
fi
log "$short: live"

# The units are installed by root (install.sh), not from the release, so that a commit cannot
# change whom the services run as. Say when the release's copies have moved on.
(cd "$release/deploy/systemd" && find . -type f -printf '%P\n') | while read -r unit; do
  if ! cmp --silent "$release/deploy/systemd/$unit" "/etc/systemd/system/$unit"; then
    log "warning: $unit differs from the installed copy; re-run deploy/install.sh"
  fi
done

# Keep the newest releases and the live one; drop the rest.
find "$RELEASES" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2- |
  tail -n +"$((KEEP + 1))" | while read -r old; do
  [[ "$old" == "$release" || "$old" == "$previous" ]] && continue
  rm -rf "$old"
done
