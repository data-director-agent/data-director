#!/usr/bin/env bash
# One pass of the deployment (deploy/README.md). Run by data-director-deploy.service as the
# datadirector user, every five minutes:
#
#   1. fetch the branch into the bare clone;
#   2. pick the newest commit on the branch that passed CI, did not fail here before and is newer
#      than the live one (pick() below); stop if there is none;
#   3. build it into its own release directory, unless the VM is short of memory (the pass waits) (uv sync, the re3data registry, npm build of
#      app/web, the browser scanner's bundle);
#   4. once no turn is running (or after DD_DEPLOY_BUSY_LIMIT_MIN), point /opt/data-director/current
#      at it and ask for data-director.target to be restarted, agents in batches (restart.sh);
#   5. if the app does not report the new commit, or lists an agent unavailable that was not
#      before, point `current` back and restart again.
#
# "Running" means the app reports the commit on /api/about, not only that `current` points at
# it: if the restart did not happen, the old processes are still serving the old commit.
#
# Settings, each with its default (set them in /etc/data-director/deploy.env):
#   DD_DEPLOY_REPO        https://github.com/data-director-agent/data-director.git
#   DD_DEPLOY_BRANCH      main
#   DD_DEPLOY_CHECK       CI passed       the check run that must have succeeded on the commit
#   DD_DEPLOY_ROOT        /opt/data-director
#   UV_PYTHON_INSTALL_DIR DD_DEPLOY_ROOT/python   where uv installs Python, for every service's user
#   DD_DEPLOY_KEEP        3               release directories kept, the live one included
#   DD_DEPLOY_DEPTH       10              commits back from the tip that a pass looks at
#   DD_DEPLOY_ABOUT_URL   http://127.0.0.1:7860/api/about   where the app names its commit
#   DD_DEPLOY_STATUS_URL  http://127.0.0.1:7860/server-status?auto   where the app counts the turns running
#   DD_DEPLOY_MIN_MEMORY_MB    600        a build waits while less memory than this is available; 0 never waits
#   DD_DEPLOY_BUSY_LIMIT_MIN   120        minutes a built release waits for the turns running to end
#   DD_DEPLOY_HEALTH_TIMEOUT   120        seconds the app has to report the new commit and its agents
#   GITHUB_TOKEN          (unset)         only for a private repository or the API rate limit
#
# A pass does nothing while DD_DEPLOY_ROOT/deploy.paused exists (deploy/README.md, "Holding
# deployments back"): empty, until it is removed; holding a time, such as 2026-11-24T18:00Z, until
# then, when the pass removes it and goes on. A file that names no time it can read holds them back
# too, so a mistyped pause still pauses.
#
# `deploy.sh --force` deploys the tip, skipping the CI check, the record of failed commits, any
# pause, the wait for memory and the wait for turns.
#
# `deploy.sh --bootstrap [sha]` is the way out when this script, the copy in the live release, is
# what stops a deployment: it points `current` at a release that is already built (sha, or the
# newest built one), restarts, and waits for the app to report it. It fetches nothing, checks
# no CI, builds nothing and records no failure. Run it from that release's own copy, as the
# deploy user or as root (deploy/README.md, "The app shows an old commit"):
#
#   sudo /opt/data-director/releases/<sha>/deploy/deploy.sh --bootstrap
set -euo pipefail

REPO="${DD_DEPLOY_REPO:-https://github.com/data-director-agent/data-director.git}"
BRANCH="${DD_DEPLOY_BRANCH:-main}"
CHECK="${DD_DEPLOY_CHECK:-CI passed}"
ROOT="${DD_DEPLOY_ROOT:-/opt/data-director}"
KEEP="${DD_DEPLOY_KEEP:-3}"
DEPTH="${DD_DEPLOY_DEPTH:-10}"
# Where uv installs Python, which each release's .venv links to: readable by every service's user,
# the model broker's among them, unlike the deploy user's home (deploy/install.sh).
export UV_PYTHON_INSTALL_DIR="${UV_PYTHON_INSTALL_DIR:-$ROOT/python}"
# /api/about answers without a session, so the check works with sign-in on (app/README.md).
ABOUT_URL="${DD_DEPLOY_ABOUT_URL:-http://127.0.0.1:7860/api/about}"
# Seconds the app has to report the new commit after a restart: the agents get 60 (wait-for-ports.sh) and the
# app then reads their cards.
HEALTH_TIMEOUT="${DD_DEPLOY_HEALTH_TIMEOUT:-120}"
# Memory and turns hold a pass back without failing it: nothing is recorded, and the next pass tries again.
MIN_MEMORY_MB="${DD_DEPLOY_MIN_MEMORY_MB:-600}"
BUSY_LIMIT_MIN="${DD_DEPLOY_BUSY_LIMIT_MIN:-120}"
STATUS_URL="${DD_DEPLOY_STATUS_URL:-http://127.0.0.1:7860/server-status?auto}"
MEMINFO="${DD_DEPLOY_MEMINFO:-/proc/meminfo}"
# Seconds after a commit's date before "no CI run at all" is reported as a problem, not a wait.
MISSING_CHECK_GRACE=1800

FORCE=0
BOOTSTRAP=0
BOOTSTRAP_SHA=""
case "${1:-}" in
  "") ;;
  --force) FORCE=1 ;;
  --bootstrap)
    BOOTSTRAP=1
    BOOTSTRAP_SHA="${2:-}"
    ;;
  *)
    echo "usage: deploy.sh [--force | --bootstrap [sha]]" >&2
    exit 2
    ;;
esac

# Root's copy, installed from the clone (install.sh), like the restart unit that runs it.
RESTART="${DD_RESTART_SCRIPT:-/usr/local/lib/data-director/restart.sh}"
BARE="$ROOT/repo.git"
RELEASES="$ROOT/releases"
CURRENT="$ROOT/current"
FAILED="$ROOT/failed-commits"
PAUSED="$ROOT/deploy.paused"

log() { echo "$*"; }
die() { echo "error: $*" >&2; exit 1; }

# The commit the running app reports, or nothing if it does not answer.
running_commit() {
  curl --fail --silent --max-time 5 "$ABOUT_URL" 2>/dev/null | jq -r '.commit // empty' 2>/dev/null || true
}

# Ask for the app and agents to be restarted. The deploy user may not restart them: root's
# data-director-restart.path unit watches a file and restarts data-director.target when it is
# written (install.sh installs the unit). The restart follows a moment after this returns, and
# healthy() waits for it, so a restart that never comes ends in the same rollback as one that fails.
# Root (a --bootstrap by hand) restarts them directly.
restart() {
  if ((EUID == 0)); then
    "$RESTART" 9>&-
    return
  fi
  systemctl is-active --quiet data-director-restart.path ||
    die "data-director-restart.path is not active, so nothing would restart data-director.target; run deploy/install.sh as root (deploy/README.md)"
  # A write, not a touch: the path unit watches for modification.
  date --utc +%FT%TZ >"$ROOT/restart-requested"
}

link() {
  ln -sfn "$1" "$ROOT/current.new"
  # Run as root, the link would be root's and the next pass, as the deploy user, could not replace it.
  if ((EUID == 0)); then chown -h --reference="$ROOT" "$ROOT/current.new"; fi
  mv -T "$ROOT/current.new" "$CURRENT"
}

# The agents the app lists as unavailable or built against another contract, one a line, sorted;
# nothing if it does not answer.
missing_agents() {
  curl --fail --silent --max-time 5 "$ABOUT_URL" 2>/dev/null |
    jq -r '((.unavailable // []) + (.incompatible // []))[]' 2>/dev/null | sort -u || true
}

# Wait until the app reports the given commit and lists no agent missing that is not in $2 (the
# agents missing before the switch), so that a release whose agent does not start is rolled back,
# and an agent that was already down does not roll back every release. The app retries the
# missing agents as /api/about is asked (dd_app.about_refresh).
healthy() {
  local deadline=$((SECONDS + HEALTH_TIMEOUT)) added=""
  while true; do
    if [[ "$(running_commit)" == "$1" ]]; then
      added="$(comm -13 <(printf '%s\n' "${2:-}" | sort -u) <(missing_agents))"
      [[ -z "$added" ]] && return 0
    fi
    if ((SECONDS >= deadline)); then
      [[ -n "$added" ]] && log "unavailable after the restart: $(tr '\n' ' ' <<<"$added")" >&2
      return 1
    fi
    sleep 2
  done
}

# One pass at a time, whether from the timer or by hand.
exec 9>"$ROOT/deploy.lock"
# Created by root, the lock would be unusable by the deploy user's next pass.
if ((EUID == 0)); then chown --reference="$ROOT" "$ROOT/deploy.lock"; fi
flock -n 9 || { log "another deployment is running"; exit 0; }

# Megabytes of memory available to start something, which counts what the kernel can reclaim;
# unlimited if the VM does not say.
available_mb() {
  awk '/^MemAvailable:/ { print int($2 / 1024); found = 1 } END { if (!found) print 1000000 }' "$MEMINFO"
}

# The number of turns the app is running, or 0 if it does not say (a pass must not wait for ever
# on an app that is down).
busy_turns() {
  local n
  n="$(curl --fail --silent --max-time 5 "$STATUS_URL" 2>/dev/null | sed -n 's/^BusyWorkers: *//p')" || true
  [[ "$n" =~ ^[0-9]+$ ]] && echo "$n" || echo 0
}

# --- Bootstrap ---------------------------------------------------------------------------------

# Point `current` at a release that is already built, restart, and wait for it. This depends on
# neither GitHub, CI nor the build, only on the release directory and a way to restart.
bootstrap() {
  [[ -d "$RELEASES" ]] || die "no releases in $RELEASES"
  local release
  if [[ -n "$BOOTSTRAP_SHA" ]]; then
    local matches=() dir
    for dir in "$RELEASES/$BOOTSTRAP_SHA"*/; do
      [[ -d "$dir" ]] && matches+=("${dir%/}")
    done
    ((${#matches[@]} == 1)) || die "\"$BOOTSTRAP_SHA\" matches ${#matches[@]} releases in $RELEASES, not one"
    release="${matches[0]}"
  else
    # The newest release that finished building (its .built is written last).
    release="$(find "$RELEASES" -mindepth 2 -maxdepth 2 -name .built -printf '%T@ %h\n' | sort -rn | sed -n 1p | cut -d' ' -f2-)"
    [[ -n "$release" ]] || die "no built release in $RELEASES"
  fi
  [[ -f "$release/.built" ]] || die "$(basename "$release") was not built to the end; nothing to bootstrap"

  local sha short previous prev_short=""
  sha="$(basename "$release")"
  short="${sha:0:12}"
  previous=""
  if [[ -L "$CURRENT" ]]; then
    previous="$(readlink -f "$CURRENT")"
    prev_short="$(basename "$previous")"
    prev_short="${prev_short:0:12}"
  fi

  if [[ "$previous" == "$release" && "$(running_commit)" == "$sha" ]]; then
    log "$short: already live"
    return
  fi

  log "$short: bootstrapping (was ${prev_short:-nothing})"
  local missing
  missing="$(missing_agents)"
  link "$release"
  if ! (restart); then
    [[ -n "$previous" ]] && link "$previous"
    exit 1
  fi
  if ! healthy "$sha" "$missing"; then
    if [[ -n "$previous" ]]; then
      log "$short: the app did not report $short at $ABOUT_URL; putting $prev_short back"
      link "$previous"
      restart
    fi
    die "$short: the app did not report $short at $ABOUT_URL"
  fi
  log "$short: live"
}

if ((BOOTSTRAP == 1)); then
  bootstrap
  exit 0
fi

# --- 0. Paused? --------------------------------------------------------------------------------

# Whether deploy.paused holds this pass back, saying so if it does. A pause whose time has passed
# is removed, so one set for a workshop cannot be forgotten.
paused() {
  [[ -e "$PAUSED" ]] || return 1
  local until end
  until="$(tr -d '[:space:]' <"$PAUSED")"
  if [[ -z "$until" ]]; then
    log "paused until $PAUSED is removed; not deploying"
    return 0
  fi
  if ! end="$(date --utc --date "$until" +%s 2>/dev/null)"; then
    log "paused: $PAUSED holds \"$until\", which is not a time, so until it is removed; not deploying"
    return 0
  fi
  if (($(date +%s) < end)); then
    log "paused until $until ($PAUSED); not deploying"
    return 0
  fi
  rm -f "$PAUSED"
  log "the pause until $until has ended; deploying again"
  return 1
}

if ((FORCE == 0)) && paused; then
  exit 0
fi

# --- 1. Fetch ----------------------------------------------------------------------------------

if [[ ! -d "$BARE" ]]; then
  git clone --quiet --bare --single-branch --branch "$BRANCH" "$REPO" "$BARE"
fi
git -C "$BARE" fetch --quiet --force "$REPO" "+refs/heads/$BRANCH:refs/heads/$BRANCH"
tip="$(git -C "$BARE" rev-parse "refs/heads/$BRANCH")"

# --- 2. Decide ---------------------------------------------------------------------------------

live=""
[[ -L "$CURRENT" ]] && live="$(basename "$(readlink "$CURRENT")")"

# The conclusion of the check on a commit: success, a state still to finish, the conclusion it
# ended with, or "missing" if CI has not run on it at all. The repository is public, so no token
# is needed: a pass makes one request for each commit it looks at (pick() below), and 60
# unauthenticated requests an hour allow about five a pass.
slug="$(sed -E 's#^(https://github.com/|ssh://git@github.com/|git@github.com:)##; s#\.git$##' <<<"$REPO")"
auth=()
[[ -n "${GITHUB_TOKEN:-}" ]] && auth=(-H "Authorization: Bearer $GITHUB_TOKEN")
check_of() {
  curl --fail --silent --show-error --max-time 30 "${auth[@]}" \
    -H "Accept: application/vnd.github+json" \
    --get --data-urlencode "check_name=$CHECK" --data-urlencode "per_page=100" \
    "https://api.github.com/repos/$slug/commits/$1/check-runs" |
    jq -r '[.check_runs[] | .conclusion // .status] | if length == 0 then "missing" else (if any(. == "success") then "success" else .[0] end) end'
}

# The newest commit on the branch that passed CI and is newer than the live one, or nothing. It
# walks back from the tip, so that a tip still in CI, or one that failed, does not hold back a
# commit before it that passed. It stops at the live commit, so it never goes back to an older
# one, and after DEPTH commits.
pick() {
  local commit short conclusion age
  while read -r commit; do
    [[ "$commit" == "$live" ]] && return
    short="${commit:0:12}"
    if [[ -f "$FAILED" ]] && grep -qx "$commit" "$FAILED"; then
      continue
    fi
    conclusion="$(check_of "$commit")" || die "could not read the checks on $short from GitHub"
    case "$conclusion" in
      success)
        echo "$commit"
        return
        ;;
      missing)
        # No run at all is not the same as a run in progress: a commit that CI never saw (pushed
        # with GITHUB_TOKEN, marked [skip ci], or during an Actions outage) waits for ever. Say
        # so once the commit is old enough that CI should have started.
        age=$(($(date +%s) - $(git -C "$BARE" log -1 --format=%ct "$commit")))
        if ((age > MISSING_CHECK_GRACE)); then
          log "$short: no \"$CHECK\" run after $((age / 60)) minutes; run the CI workflow on main by hand, or deploy with --force" >&2
        else
          log "$short: \"$CHECK\" has not started" >&2
        fi
        ;;
      queued | in_progress | pending | waiting | requested)
        log "$short: \"$CHECK\" has not finished" >&2
        ;;
      *)
        # Not recorded as failed: if CI is re-run and passes, the commit is deployed then.
        log "$short: \"$CHECK\" ended $conclusion; not deploying it" >&2
        ;;
    esac
  done < <(git -C "$BARE" rev-list --first-parent --max-count="$DEPTH" "$tip")
}

if ((FORCE == 1)); then
  sha="$tip"
else
  sha="$(pick)"
fi

if [[ -z "$sha" || "$sha" == "$live" ]]; then
  # Linked but not running: an earlier pass switched the link and then could not restart.
  running="$(running_commit)"
  if [[ -n "$live" && -n "$running" && "$running" != "$live" ]]; then
    log "${live:0:12}: is current but the app reports ${running:0:12}; restarting"
    missing="$(missing_agents)"
    restart
    healthy "$live" "$missing" || die "${live:0:12}: the app did not report ${live:0:12} at $ABOUT_URL after a restart"
    log "${live:0:12}: live"
  fi
  exit 0
fi
short="${sha:0:12}"

# --- 3. Build ----------------------------------------------------------------------------------

# A release is built where it will run: dd_app finds app/config and app/web/dist beside its own
# source, and the virtual environment records its own path, so neither can be moved afterwards.
release="$RELEASES/$sha"
if [[ ! -f "$release/.built" ]]; then
  # A build beside a VM that is already swapping makes it worse (#1616). Wait, and record nothing.
  if ((FORCE == 0 && MIN_MEMORY_MB > 0)) && (($(available_mb) < MIN_MEMORY_MB)); then
    log "$short: not building: $(available_mb) MB of memory is available, less than DD_DEPLOY_MIN_MEMORY_MB ($MIN_MEMORY_MB); will try again"
    exit 0
  fi
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
      # Sources that agents build outside git, such as the repository advisor's re3data registry
      # (dd-sources, sdk/src/dd_sdk/sources.py). What they are built from is kept outside the
      # releases, so it is downloaded once per pin, not once per release.
      uv run --no-sync dd-sources prepare --cache-dir "$ROOT/cache/sources" &&
      cd app/web &&
      npm ci --no-audit --no-fund --loglevel=error &&
      npm run build --silent &&
      rm -rf node_modules &&
      # The browser scanner's bundle (inventory/browser/README.md, Browser bundle), served from
      # dist/inventory-bundle/. Its wheels are kept outside the releases, as the sources are, and
      # each is checked against its lock whether it was downloaded or read back.
      cd ../../inventory/browser &&
      mkdir -p "$ROOT/cache/inventory-wheels" .cache &&
      ln -sfn "$ROOT/cache/inventory-wheels" .cache/wheels &&
      npm ci --no-audit --no-fund --loglevel=error &&
      npm run bundle --silent &&
      cp -R dist/inventory-bundle ../../app/web/dist/ &&
      rm -rf node_modules dist .cache
  ) || die "$short: build failed"
  echo "$sha" >"$release/.built"
fi

# --- 4. Switch ---------------------------------------------------------------------------------

# A restart cuts off the turns running, so wait for them to end, up to a limit so that a deployment
# with people always at work is not held back for ever. The built release is kept: the next pass
# switches to it without building.
if ((FORCE == 0)); then
  built_age=$((($(date +%s) - $(stat -c %Y "$release/.built")) / 60))
  turns="$(busy_turns)"
  if ((turns > 0 && built_age < BUSY_LIMIT_MIN)); then
    log "$short: built, but $turns turn(s) are running; will switch when they end (or after $((BUSY_LIMIT_MIN - built_age)) more minutes)"
    exit 0
  fi
fi

previous=""
[[ -L "$CURRENT" ]] && previous="$(readlink -f "$CURRENT")"
missing="$(missing_agents)"

was="${live:0:12}"
log "$short: going live (was ${was:-nothing})"
link "$release"
# A restart that could not be requested leaves the old processes running: put the link back so
# that the next pass tries again, instead of taking the link for the running release.
if ! (restart); then
  [[ -n "$previous" ]] && link "$previous"
  exit 1
fi

# --- 5. Check, or roll back --------------------------------------------------------------------

if ! healthy "$sha" "$missing"; then
  echo "$sha" >>"$FAILED"
  if [[ -n "$previous" ]]; then
    log "$short: the app did not report $short at $ABOUT_URL; rolling back to ${live:0:12}"
    link "$previous"
    restart
    healthy "$live" "$missing" || die "${live:0:12} did not answer after the rollback either"
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
