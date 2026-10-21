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
HTPASSWD=/etc/nginx/data-director.htpasswd

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
apt-get install -y -q git curl jq ca-certificates gnupg nginx apache2-utils certbot python3-certbot-nginx

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
new_file "$ETC/app.env" "$SRC/app/env.example"
new_file "$ETC/agents.env"
new_file "$ETC/deploy.env" "$SRC/deploy/deploy.env.example"

step "Restart rule"
# deploy.sh, running as $USER_NAME, may restart the services and do nothing else as root.
rule="$(mktemp)"
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/bin/systemctl restart data-director.target" >"$rule"
visudo -cqf "$rule"
install -m 0440 "$rule" /etc/sudoers.d/data-director
rm -f "$rule"

step "systemd units"
install -m 0644 "$SRC"/deploy/systemd/* /etc/systemd/system/
systemctl daemon-reload

step "NGINX site for $domain"
sed "s/SERVER_NAME/$domain/" "$SRC/deploy/nginx/data-director.conf" \
  >/etc/nginx/sites-available/data-director
ln -sfn /etc/nginx/sites-available/data-director /etc/nginx/sites-enabled/data-director
if [[ ! -s "$HTPASSWD" ]]; then
  if [[ -t 0 ]]; then
    read -rp "First user name for the site's password: " web_user
    htpasswd -B -c "$HTPASSWD" "$web_user"
  else
    echo "warning: no $HTPASSWD; create it with: sudo htpasswd -B -c $HTPASSWD NAME" >&2
  fi
fi
[[ -e "$HTPASSWD" ]] && chown root:www-data "$HTPASSWD" && chmod 0640 "$HTPASSWD"
nginx -t
systemctl reload nginx

# The app does not start without whom it acts for (app/README.md), so the first deployment
# waits until it is set.
if ! grep -qE '^DD_PRINCIPAL_ID=.+' "$ETC/app.env" || ! grep -qE '^DD_PRINCIPAL_NAME=.+' "$ETC/app.env"; then
  echo
  echo "Set DD_PRINCIPAL_ID and DD_PRINCIPAL_NAME in $ETC/app.env, then run this again."
  exit 0
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
echo "Done. The site is http://$domain/ (behind the password)."
echo "For HTTPS: sudo certbot --nginx -d $domain"
