#!/usr/bin/env bash
# Set up an Ubuntu VM to run the Data Director and keep it deployed (deploy/README.md). Run as
# root from a clone of the repository:
#
#   sudo deploy/install.sh --domain data-director.example.ac.uk [--gateway]
#
# --gateway also runs the LiteLLM gateway on the VM, in Docker, and sends the model broker's
# deployment-paid calls through it (deploy/README.md, "The LiteLLM gateway"). Once given, it stays
# on: later runs keep the gateway up to date without it.
#
# It is safe to run again, and running it again is how a change to the systemd units or the
# NGINX site reaches the VM. It never overwrites the files in /etc/data-director.
set -euo pipefail

# The uv the VM builds with. CI uses the latest, so raise this when uv.lock needs a newer one.
UV_VERSION="${UV_VERSION:-0.9.5}"
# The Node major the shell needs (app/web/package.json, "engines").
NODE_MAJOR=22

SRC="$(cd "$(dirname "$0")/.." && pwd)"
USER_NAME=datadirector
# The model broker's own user (deploy/systemd/data-director-model-broker.service).
BROKER_USER=data-director-broker
ROOT=/opt/data-director
# The Python interpreters uv installs, which every release's .venv links to. They are kept here,
# readable by every service's user, not in $STATE: the model broker runs as a user of its own,
# which cannot enter $STATE.
PYTHONS="$ROOT/python"
STATE=/var/lib/data-director
ETC=/etc/data-director

GATEWAY_UNIT=data-director-llm-gateway.service

domain=""
gateway=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) domain="$2"; shift 2 ;;
    --gateway) gateway=true; shift ;;
    *) echo "usage: $0 --domain NAME [--gateway]" >&2; exit 2 ;;
  esac
done
[[ -n "$domain" ]] || { echo "usage: $0 --domain NAME [--gateway]" >&2; exit 2; }
[[ $EUID -eq 0 ]] || { echo "run as root (sudo)" >&2; exit 1; }

step() { echo; echo "==> $*"; }

step "Packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
# postgresql-client: pg_dump and pg_restore, which back up and restore a store kept in a database.
apt-get install -y -q git curl jq ca-certificates gnupg nginx certbot python3-certbot-nginx \
  postgresql-client

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

step "The data-director command"
# `sudo data-director doctor` checks this deployment and `data-director secret` gives an agent a
# secret (scripts/dd.py, deploy/README.md). It runs from this clone, which root controls, never
# from a release, which a commit to the branch can change.
install -m 0755 /dev/stdin /usr/local/bin/data-director <<WRAPPER
#!/bin/sh
exec /usr/local/bin/uv run --quiet --script "$SRC/scripts/dd.py" --target vm "\$@"
WRAPPER

step "The backup script"
# data-director-backup.service runs this copy, installed by root from the clone like the units, so
# that a commit to the branch cannot change what runs as root (deploy/README.md, "Backups").
install -d -m 0755 /usr/local/lib/data-director
install -m 0755 "$SRC/deploy/backup.sh" /usr/local/lib/data-director/backup.sh
install -m 0644 "$SRC/deploy/stores.sh" /usr/local/lib/data-director/stores.sh
install -m 0644 "$SRC/deploy/gateway-store.sh" /usr/local/lib/data-director/gateway-store.sh

step "User and directories"
if ! id "$USER_NAME" &>/dev/null; then
  useradd --system --home-dir "$STATE" --create-home --shell /usr/sbin/nologin "$USER_NAME"
fi
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0755 "$ROOT" "$ROOT/releases" "$PYTHONS"
install -d -o "$USER_NAME" -g "$USER_NAME" -m 0750 "$STATE" "$STATE/runs" "$STATE/projects" \
  "$STATE/workbench-runs"
install -d -o root -g "$USER_NAME" -m 0750 "$ETC"

# Secrets and settings: root writes them, the services read them.
new_file() { # new_file DEST [SOURCE]
  [[ -e "$1" ]] && return
  if [[ -n "${2:-}" ]]; then cp "$2" "$1"; else : >"$1"; fi
  chown root:"$USER_NAME" "$1"
  chmod 0640 "$1"
  echo "created $1"
}
setting() { sed -n "s/^$1=//p" "${2:-$ETC/app.env}" | tail -n 1; }
fill() { # fill FILE NAME VALUE: set NAME in FILE if it is empty there; an operator's value stays
  [[ -n "$(setting "$2" "$1")" ]] && return
  if grep -qE "^$2=" "$1"; then
    sed -i "s|^$2=.*|$2=$3|" "$1"
  else
    echo "$2=$3" >>"$1"
  fi
}
new_file "$ETC/app.env" "$SRC/config/examples/app.env"
# Where people reach the app is known from --domain, and ORCID needs it as the redirect URI's base.
if ! grep -qE '^DD_APP_PUBLIC_URL=' "$ETC/app.env"; then
  echo "DD_APP_PUBLIC_URL=https://$domain" >>"$ETC/app.env"
fi
new_file "$ETC/agents.env"
# The workbench's settings: its own file, so that nothing of the app's reaches it.
new_file "$ETC/workbench.env" "$SRC/config/examples/workbench.env"
# Each agent's own settings, and its secrets (docs/specs/policy-and-identity.md). A secret is root's alone: systemd
# hands it to the one unit that loads it (LoadCredential=).
install -d -o root -g "$USER_NAME" -m 0750 "$ETC/agents"
install -d -o root -g root -m 0700 "$ETC/credentials" "$ETC/credentials/app"
# The model broker runs as a user of its own, which no other service shares, and reads its secrets
# from its own credentials directory (docs/guide/operations/model-broker.md). Its unit is installed
# below but not enabled: own model accounts are off until an operator turns them on.
if ! id "$BROKER_USER" &>/dev/null; then
  useradd --system --no-create-home --home-dir /var/lib/data-director-model-broker \
    --shell /usr/sbin/nologin "$BROKER_USER"
fi
install -d -o root -g root -m 0700 "$ETC/credentials/model-broker"
new_file "$ETC/model-broker.env" "$SRC/config/examples/model-broker.env"
# The broker checks grants against the keys the app publishes, on the app's loopback address.
fill "$ETC/model-broker.env" DD_BROKER_HARNESS_JWKS_URL \
  "http://127.0.0.1:$(setting DD_APP_PORT | grep . || echo 7860)/.well-known/jwks.json"
new_file "$ETC/deploy.env" "$SRC/deploy/deploy.env.example"
new_file "$ETC/backup.env" "$SRC/deploy/backup.env.example"
# Backups hold every secret, so their directory is root's alone.
backups="$(sed -n 's/^DD_BACKUP_DIR=//p' "$ETC/backup.env" | tail -n 1)"
install -d -o root -g root -m 0700 "${backups:-/var/backups/data-director}"
# What this instance runs: `data-director apply`, below, makes it so (scripts/ddtool/deployment.py).
if [[ ! -e "$ETC/deployment.yaml" ]]; then
  new_file "$ETC/deployment.yaml" "$SRC/config/examples/deployment.yaml"
  name="${domain%%.*}"
  sed -i "s/^name: .*/name: ${name,,}/" "$ETC/deployment.yaml"
fi

step "systemd units"
(cd "$SRC/deploy/systemd" && find . -type f -printf '%P\n') | while read -r unit; do
  install -D -m 0644 "$SRC/deploy/systemd/$unit" "/etc/systemd/system/$unit"
done

# A release built before the interpreters moved to $PYTHONS links to one in $STATE, which the model
# broker's user cannot reach. Rebuild the live release's .venv so that it links to $PYTHONS; the
# packages come from uv's cache. Older releases kept for rollback still link to $STATE, which
# stays, so they run as before, all but the broker.
live="$(readlink -f "$ROOT/current" 2>/dev/null || true)"
if [[ -n "$live" && -d "$live/.venv" ]] &&
  [[ "$(readlink -f "$live/.venv/bin/python")" == "$STATE"/* ]]; then
  step "Rebuilding the live release's Python environment in $PYTHONS"
  # shellcheck disable=SC2016 # expanded by the inner shell
  runuser -u "$USER_NAME" -- env HOME="$STATE" UV_PYTHON_INSTALL_DIR="$PYTHONS" \
    PATH=/usr/local/bin:/usr/bin:/bin \
    bash -c 'cd "$1" && rm -rf .venv && uv sync --locked --no-dev --quiet' _ "$live"
  echo "rebuilt $live/.venv"
  systemctl daemon-reload
  systemctl try-restart data-director.target
fi

step "What $ETC/deployment.yaml says this instance runs"
# The profile, the drop-ins that start each agent and make the app wait for it, and each
# agent's credentials drop-in (deploy/credentials.sh), from deployment.yaml and the live
# release's agents.yaml. It stops any agent that no longer runs. It refuses, and so stops this
# script, if deployment.yaml turns on an agent that calls a model before it has its key.
/usr/local/bin/data-director apply
systemctl daemon-reload
# deploy.sh, running as $USER_NAME, cannot restart the services. It writes
# $ROOT/restart-requested instead, and root's path unit restarts them: it may ask for that
# restart and for nothing else, as the sudo rule it replaces did.
systemctl enable --now data-director-restart.path

# A VM that runs the gateway keeps running it, and gets this clone's copy of it on every run.
if systemctl is-enabled --quiet "$GATEWAY_UNIT" 2>/dev/null; then
  gateway=true
fi
if [[ "$gateway" == true ]]; then
  step "LiteLLM gateway, on the VM's loopback only, port 4000"
  # deploy/llm-gateway/scripts/systemd.sh says how it runs and where its settings are.
  apt-get install -y -q docker.io docker-compose-v2
  systemctl enable --now docker.service
  # Docker runs what compose.yaml says as root, so the unit runs root's copy from this clone.
  lib_gateway=/usr/local/lib/data-director/llm-gateway
  install -d -m 0755 "$lib_gateway"
  install -m 0644 "$SRC/deploy/llm-gateway/compose.yaml" "$SRC/deploy/llm-gateway/config.yaml" "$lib_gateway/"
  install -m 0755 "$SRC/deploy/llm-gateway/scripts/systemd.sh" "$lib_gateway/systemd.sh"
  new_file "$ETC/llm-gateway.env" "$SRC/config/examples/llm-gateway.env"
  # The gateway's own secrets, made once. The salt key encrypts what the gateway stores, so it
  # must never change: one that exists is kept.
  gateway_credentials="$ETC/credentials/llm-gateway"
  install -d -o root -g root -m 0700 "$gateway_credentials"
  for secret in litellm-master-key litellm-salt-key postgres-password; do
    if [[ ! -s "$gateway_credentials/$secret" ]]; then
      (umask 077 && printf 'sk-%s' "$(openssl rand -hex 32)" >"$gateway_credentials/$secret")
      echo "created $gateway_credentials/$secret"
    fi
  done
  systemctl daemon-reload
  systemctl enable "$GATEWAY_UNIT"
  # restart, not start: a run of install.sh is how a new compose.yaml or config.yaml takes effect.
  systemctl restart "$GATEWAY_UNIT"

  # The model broker's key for the gateway, made once and tagged so that the gateway's spend
  # reports show the broker's calls (deploy/llm-gateway/README.md, "With the model broker").
  broker_key="$ETC/credentials/model-broker/gateway-api-key"
  if [[ ! -s "$broker_key" ]]; then
    made="$(LITELLM_URL=http://127.0.0.1:4000 \
      LITELLM_MASTER_KEY="$(<"$gateway_credentials/litellm-master-key")" \
      python3 "$SRC/deploy/llm-gateway/scripts/admin.py" key create model-broker \
      --tags service:model-broker | sed -n 's/^key: //p')"
    [[ "$made" == sk-* ]] || { echo "could not make the model broker's gateway key" >&2; exit 1; }
    (umask 077 && printf '%s' "$made" >"$broker_key")
    echo "created $broker_key"
  fi
  # The broker uses that key for every provider the deployment pays for. A key an operator has
  # set in an override of the unit (systemctl edit) still comes after this and wins.
  install -d -m 0755 /etc/systemd/system/data-director-model-broker.service.d
  install -m 0644 /dev/stdin /etc/systemd/system/data-director-model-broker.service.d/llm-gateway.conf <<DROPIN
# Written by deploy/install.sh --gateway: the deployment's calls go through the LiteLLM gateway,
# with the broker's own gateway key ($broker_key).
[Unit]
Wants=$GATEWAY_UNIT
After=$GATEWAY_UNIT

[Service]
LoadCredential=gateway-api-key:$broker_key
Environment=ANTHROPIC_API_KEY_FILE=gateway-api-key
Environment=OPENAI_API_KEY_FILE=gateway-api-key
Environment=GEMINI_API_KEY_FILE=gateway-api-key
Environment=DD_MODEL_API_KEY_FILE=gateway-api-key
DROPIN
  fill "$ETC/model-broker.env" DD_BROKER_DEPLOYMENT_BASE_URL http://127.0.0.1:4000
  systemctl daemon-reload
  systemctl try-restart data-director-model-broker.service
  provider_keys=("$gateway_credentials"/*-api-key)
  if [[ ! -e "${provider_keys[0]}" ]]; then
    echo "The gateway has no provider key yet. Give it one, which restarts it:"
    echo "  sudo data-director secret set llm-gateway anthropic-api-key"
  fi
fi

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
  runuser -u "$USER_NAME" -- env HOME="$STATE" UV_PYTHON_INSTALL_DIR="$PYTHONS" \
    PATH=/usr/local/bin:/usr/bin:/bin \
    bash -c 'set -a; source "$1"; set +a; exec "$2"' _ "$ETC/deploy.env" "$ROOT/first-deploy.sh"
  rm -f "$ROOT/first-deploy.sh"
fi

step "Enabling the services, the deployment timer and the backup timer"
systemctl enable --now data-director.target data-director-deploy.timer data-director-backup.timer

step "Admin service, on the VM's loopback only, port 8200"
# Read-only and with no sign-in, so it listens on 127.0.0.1 alone and NGINX does not serve it;
# operators reach it through an SSH tunnel (docs/guide/operations/admin.md). It needs nothing set.
systemctl enable --now data-director-admin.service
echo "The admin service is http://127.0.0.1:8200/ on this VM. From your machine:"
echo "  ssh -N -L 8200:127.0.0.1:8200 <you>@$domain   then open http://localhost:8200"

step "Workbench, for admins, at https://$domain:8443/"
# The workbench uses the app's ORCID client and is reached on port 8443. install.sh fills what it
# knows into an empty setting, and leaves an operator's value alone.
fill "$ETC/workbench.env" DD_OIDC_ISSUER "$(setting DD_OIDC_ISSUER)"
fill "$ETC/workbench.env" DD_OIDC_CLIENT_ID "$(setting DD_OIDC_CLIENT_ID)"
fill "$ETC/workbench.env" DD_WORKBENCH_PUBLIC_URL "https://$domain:8443"
# It admits only the ORCID iDs listed and does not start with none, so it is enabled once there is
# one (deploy/README.md).
if [[ -n "$(setting DD_WORKBENCH_ADMINS "$ETC/workbench.env")" ]]; then
  systemctl enable --now data-director-workbench.service
  echo "The workbench is https://$domain:8443/ for the admins in $ETC/workbench.env."
else
  systemctl disable --now data-director-workbench.service 2>/dev/null || true
  echo "The workbench is not running. To run it:"
  echo "  - add the redirect URI https://$domain:8443/api/sign-in/callback to the ORCID client;"
  echo "  - set DD_WORKBENCH_ADMINS in $ETC/workbench.env to the admins' ORCID iDs;"
  echo "  - ask for TCP port 8443 to be open to the VM;"
  echo "and run this again."
fi

echo
echo "Done. The site is https://$domain/ and people sign in with ORCID."
echo "Check the deployment at any time with: sudo data-director doctor, or the admin service."
