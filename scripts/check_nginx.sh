#!/usr/bin/env bash
# Set up deploy/nginx/data-director.conf as deploy/install.sh does, in front of a stand-in for
# the app on 127.0.0.1:7860, and check that the proxy does what the config says: a password for
# everything, /a2a and the agent card closed, the forwarded headers set, the body size limit. The
# "NGINX reverse proxy" job in .github/workflows/ci.yml runs it.
#
# It changes /etc/nginx, so run it as root on a throwaway Debian or Ubuntu host with nginx,
# apache2-utils, curl and python3 installed: a CI runner, or a container.
#
#   sudo bash scripts/check_nginx.sh
set -euo pipefail

src=$(cd "$(dirname "$0")/.." && pwd)
user=ci
password=ci-password
url=http://127.0.0.1
status=0

fail() {
  echo "::error::$*"
  status=1
}

# Ubuntu's packaged site is the default_server on :80; without this it, not ours, would answer a
# request for any other host name.
rm -f /etc/nginx/sites-enabled/default
sed "s/SERVER_NAME/localhost/" "$src/deploy/nginx/data-director.conf" \
  >/etc/nginx/sites-available/data-director
ln -sfn /etc/nginx/sites-available/data-director /etc/nginx/sites-enabled/data-director
htpasswd -B -b -c /etc/nginx/data-director.htpasswd "$user" "$password" 2>/dev/null
chown root:www-data /etc/nginx/data-director.htpasswd
chmod 0640 /etc/nginx/data-director.htpasswd

# The stand-in app answers every request with the request headers it received.
python3 - <<'PY' &
from http.server import BaseHTTPRequestHandler, HTTPServer


class Echo(BaseHTTPRequestHandler):
    def do_GET(self):
        body = str(self.headers).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *args):
        pass


HTTPServer(("127.0.0.1", 7860), Echo).serve_forever()
PY
upstream=$!
trap 'kill "$upstream"' EXIT
bash "$src/deploy/wait-for-ports.sh" 10 7860

nginx -t
if [[ -s /run/nginx.pid ]] && kill -0 "$(cat /run/nginx.pid)" 2>/dev/null; then
  nginx -s reload
else
  nginx
fi
sleep 1

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
expect() {
  local want=$1 what=$2
  shift 2
  local got
  got=$(code "$@")
  [[ "$got" == "$want" ]] || fail "$what: expected $want, got $got"
}

expect 401 "/ without a password" "$url/"
expect 401 "/ with a wrong password" -u "$user:wrong" "$url/"
expect 200 "/ with the password" -u "$user:$password" "$url/"
expect 404 "/a2a" -u "$user:$password" "$url/a2a"
expect 404 "/.well-known/agent-card.json" -u "$user:$password" "$url/.well-known/agent-card.json"
expect 413 "a body over 2 MB" -u "$user:$password" \
  -H 'Content-Type: application/json' --data-binary @<(head -c 3000000 /dev/zero | tr '\0' a) \
  "$url/"
expect 401 "another host name without a password" -H 'Host: elsewhere.example' "$url/"

headers=$(curl -s -u "$user:$password" "$url/")
grep -qi '^X-Forwarded-Proto: http' <<<"$headers" || fail "X-Forwarded-Proto not passed to the app"
grep -qi '^X-Forwarded-For: 127.0.0.1' <<<"$headers" || fail "X-Forwarded-For not passed to the app"
grep -qi '^Host: 127.0.0.1' <<<"$headers" || fail "Host not passed to the app"
if curl -s -H 'Host: elsewhere.example' "$url/" | grep -qi 'welcome to nginx'; then
  fail "the packaged default site still answers"
fi

[[ $status -eq 0 ]] && echo "nginx: every check passed"
exit "$status"
