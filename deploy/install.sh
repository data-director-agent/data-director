#!/usr/bin/env bash
# Set up an Ubuntu VM to run the Data Director and keep it deployed (deploy/README.md). Run as
# root from a clone of the repository:
#
#   sudo deploy/install.sh --domain data-director.example.ac.uk
#
# It is safe to run again, and running it again is how a change to the systemd units or the
# NGINX site reaches the VM. It never overwrites the files in /etc/data-director or the
# password file.
set -euo pipefail

# The uv the VM builds with. CI uses the latest, so raise this when uv.lock needs a newer one.
UV_VERSION="${UV_VERSION:-0.9.5}"
# The Node major the shell needs (app/web/package.json, "engines").
NODE_MAJOR=22

SRC="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME=datadirector
ROOT=/opt/data-director
STATE=/var/lib/data-director
ETC=/etc/data-director

domain=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) domain="$2"; shift 2 ;;
    *) echo "usage: $0 --domain NAME" >&2; exit 2 ;;
  esac
done
[[ -n "$domain" ]] || { echo "usage: $0 --domain NAME" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "run as root (sudo)" >&2; exit 1; }

step() { echo; echo "==> $*"; }

step "Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q git curl jq ca-certificates gnupg nginx certbot python3-certbot-nginx

if ! node --version 2>/dev/null | grep -qE "^v(2[2-9]|[3-9][0-9])\."; then
  step "Node $NODE_MAJOR (NodeSource)"
  install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key |
    gpg --dearmor --yes -o /etc/apt/keyrings/nodesource.gpg
  echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" \
    >/etc/apt/sources.list.d/nodesource.list
  apt-get update -q
  apt-get install -y -q nodejs
fi

if [[ "$(/usr/local/bin/uv --version 2>/dev/null)" != "uv $UV_VERSION"* ]]; then
  step "uv $UV_VERSION"
  curl -fsSL "https://astral.sh/uv/$UV_VERSION/install.sh" |
    env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
fi

step "User and directories"
if ! id "$USER_NAME" &>/dev/null; then
  useradd --system --home-dir "$STATE" --create-home --shell /usr/sbin/nologin "$USER_NAME"
fi
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0755 "$ROOT" "$ROOT/releases"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 "$STATE" "$STATE/runs"
install -d -o root -g "$USER_NAME" -m 0750 "$ETC"

# Secrets and settings: root writes them, the services read them.
new_file() { # new_file DEST [SOURCE]
  [[ -e "$1" ]] && return
  if [[ -n "${2:-}" ]]; then cp "$2" "$1"; else : >"$1"; fi
  chown root:"$USER_NAME" "$1"
  chmod 0640 "$1"
  echo "created $1"
}
new_file "$ETC/app.env" "$SRC/config/examples/app.env"
# Where people reach the app is known from --domain, and ORCID needs it as the redirect URI's base.
if ! grep -qE '^DD_APP_PUBLIC_URL=' "$ETC/app.env"; then
  echo "DD_APP_PUBLIC_URL=https://$domain" >>"$ETC/app.env"
fi
new_file "$ETC/agents.env"
# Each agent's own settings, and model keys (docs/specs/policy-and-identity.md). A key file is root's alone: systemd hands
# it to the one unit that loads it (LoadCredential=).
install -d -o root -g "$USER_NAME" -m 0750 "$ETC/agents"
install -d -o root -g root -m 0700 "$ETC/credentials" "$ETC/credentials/app"
new_file "$ETC/deploy.env" "$SRC/deploy/deploy.env.example"

step "Restart rule"
# deploy.sh, running as $USER_NAME, may restart the services and do nothing else as root.
rule="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl restart data-director.target" >"$rule"
visudo -cqf "$rule"
install -m 0440 "$rule" /etc/sudoers.d/data-director
rm -f "$rule"

step "systemd units"
(cd "$SRC/deploy/systemd" && find . -type f -printf '%P\n') | while read -r unit; do
  install -D -m 0644 "$SRC/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done

# An agent that is no longer deployed (no deploy/agents/<name>.env), such as one renamed, is
# stopped and loses its drop-ins; otherwise it would go on holding its port.
for unit in $(systemctl list-units --all --plain --no-legend 'data-director-agent@*.service' | awk '{print $1}') \
  $(cd /etc/systemd/system && compgen -G 'data-director-agent@*.service.d' | sed 's/\.d$//'); do
  name="${unit#data-director-agent@}"
  name="${name%.service}"
  [[ -f "$SRC/deploy/agents/$name.env" ]] && continue
  echo "$unit: no longer deployed; stopping it"
  systemctl stop "$unit" || true
  rm -rf "/etc/systemd/system/$unit.d"
done

# A model key's drop-in, only for an agent whose key is in place (deploy/credentials/).
for conf in "$SRC"/deploy/credentials/*.conf; do
  name="$(basename "$conf" .conf)"
  dropin="/etc/systemd/system/data-director-agent@$name.service.d/credentials.conf"
  if [[ -s "$ETC/credentials/$name/anthropic-api-key" ]]; then
    echo "$name: model key in place"
    install -D -m 0644 "$conf" "$dropin"
  else
    rm -f "$dropin"
    rmdir "$(dirname "$dropin")" 2>/dev/null || true
  fi
done
systemctl daemon-reload

step "Certificate for $domain"
# The site names certbot's certificate, so it must exist before the site is installed. certbot
# answers the challenge through whatever NGINX serves on port 80 at the time, and renews the
# same way; the hook reloads NGINX onto the renewed certificate.
cert="/etc/letsencrypt/live/$domain/fullchain.pem"
if [[ ! -s "$cert" ]]; then
  if [[ -t 0 ]]; then
    certbot certonly --nginx -d "$domain"
  else
    echo "no $cert; get it with: sudo certbot certonly --nginx -d $domain" >&2
    exit 1
  fi
fi
install -D -m 0755 /dev/stdin /etc/letsencrypt/renewal-hooks/deploy/reload-nginx <<'HOOK'
#!/bin/sh
exec systemctl reload nginx
HOOK

step "NGINX site for $domain"
# The packaged default site would answer any request for another host name.
rm -f /etc/nginx/sites-enabled/default
sed "s/SERVER_NAME/$domain/" "$SRC/deploy/nginx/data-director.conf" \
  >/etc/nginx/sites-available/data-director
ln -sfn /etc/nginx/sites-available/data-director /etc/nginx/sites-enabled/data-director
nginx -t
systemctl reload nginx

# The app signs people in with ORCID and does not start without the client (docs/guide/operations/
# configuration.md), so the first deployment waits until it is in place.
setting() { sed -n "s/^$1=//p" "$ETC/app.env" | tail -n 1; }
missing=()
for name in DD_OIDC_ISSUER DD_OIDC_CLIENT_ID DD_APP_PUBLIC_URL; do
  [[ -n "$(setting "$name")" ]] || missing+=("$name in $ETC/app.env")
done
[[ -s "$ETC/credentials/app/orcid-client-secret" ]] || missing+=("the client secret in $ETC/credentials/app/orcid-client-secret")
if [[ -n "$(setting DD_PRINCIPAL_ID)$(setting DD_PRINCIPAL_NAME)" ]]; then
  echo "Remove DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME from $ETC/app.env: the app stops at start-up" >&2
  echo "if it is given both a sign-in provider and an operator." >&2
  exit 1
fi
if ((${#missing[@]})); then
  echo
  echo "Register an ORCID client with the redirect URI https://$domain/api/sign-in/callback, then set:"
  printf '  %s\n' "${missing[@]}"
  echo "and run this again."
  exit 0
fi

# Sign-in starts the run store afresh, so that no run recorded for an operator sits beside runs
# for people who signed in (docs/specs/policy-and-identity.md). A deployment that ran before is
# stopped and its store set aside, once.
if [[ ! -e "$STATE/.sign-in" ]]; then
  if [[ -L "$ROOT/current" ]] && [[ -n "$(ls -A "$STATE/runs")" ]]; then
    step "Setting aside the runs recorded before sign-in"
    systemctl stop data-director.target
    aside="$STATE/runs.before-sign-in-$(date +%Y%m%d)"
    mv "$STATE/runs" "$aside"
    install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 "$STATE/runs"
    echo "moved the old run store to $aside"
  fi
  install -m 0640 -o root -g "$USER_NAME" /dev/null "$STATE/.sign-in"
fi

if [[ ! -L "$ROOT/current" ]]; then
  step "First deployment (this builds the first release and can take some minutes)"
  # deploy.sh normally runs from the live release; there is none yet, so run this clone's,
  # copied where the service user can read it (a clone in a home directory may not be).
  install -m 0755 "$SRC/deploy/deploy.sh" "$ROOT/first-deploy.sh"
  # shellcheck disable=SC2016 # expanded by the inner shell
  runuser -u "$USER_NAME" -- env HOME="$STATE" PATH=/usr/local/bin:/usr/bin:/bin \
    bash -c 'set -a; source "$1"; set +a; exec "$2"' _ "$ETC/deploy.env" "$ROOT/first-deploy.sh"
  rm -f "$ROOT/first-deploy.sh"
fi

step "Enabling the services and the deployment timer"
systemctl enable --now data-director.target data-director-deploy.timer

echo
echo "Done. The site is https://$domain/ and people sign in with ORCID."
