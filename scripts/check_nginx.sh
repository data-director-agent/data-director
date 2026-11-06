#!/usr/bin/env bash
# Set up deploy/nginx/data-director.conf as deploy/install.sh does, in front of stand-ins for
# the app on 127.0.0.1:7860 and the workbench on 127.0.0.1:8000, and check that the proxy does
# what the config says: HTTP redirected to HTTPS, TLS 1.3 alone, HSTS, no password of its own (the
# app and the workbench sign people in), /a2a and the agent card closed, the forwarded headers set,
# the body size limit, and port 8443 reaching the workbench and nothing else. The "NGINX reverse proxy" job in
# .github/workflows/ci.yml runs it.
#
# It changes /etc/nginx and /etc/letsencrypt, so run it as root on a throwaway Debian or Ubuntu
# host with nginx, curl, openssl and python3 installed: a CI runner, or a
# container. A self-signed certificate stands in for certbot's.
#
#   sudo bash scripts/check_nginx.sh
set -euo pipefail

src=$(cd "$(dirname "$0")/.." && pwd)
url=https://127.0.0.1
status=0

fail() {
  echo "::error::$*"
  status=1
}

# Ubuntu's packaged site is the default_server on :80; without this it, not ours, would answer a
# request for any other host name.
rm -f /etc/nginx/sites-enabled/default
live=/etc/letsencrypt/live/localhost
mkdir -p "$live"
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 1 \
  -subj /CN=localhost -keyout "$live/privkey.pem" -out "$live/fullchain.pem" 2>/dev/null
sed "s/SERVER_NAME/localhost/" "$src/deploy/nginx/data-director.conf" \
  >/etc/nginx/sites-available/data-director
ln -sfn /etc/nginx/sites-available/data-director /etc/nginx/sites-enabled/data-director

# The stand-ins answer every request with the port they serve and the request headers received.
python3 - <<'PY' &
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


class Echo(BaseHTTPRequestHandler):
    def do_GET(self):
        body = f"Upstream: {self.server.server_port}\n{self.headers}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    do_POST = do_GET

    def log_message(self, *args):
        pass


workbench = HTTPServer(("127.0.0.1", 8000), Echo)
threading.Thread(target=workbench.serve_forever, daemon=True).start()
HTTPServer(("127.0.0.1", 7860), Echo).serve_forever()
PY
upstream=$!
trap 'kill "$upstream"' EXIT
bash "$src/deploy/wait-for-ports.sh" 10 7860 8000

nginx -t
if [[ -s /run/nginx.pid ]] && kill -0 "$(cat /run/nginx.pid)" 2>/dev/null; then
  nginx -s reload
else
  nginx
fi
sleep 1

# A refused connection or handshake is 000, not an error.
code() { curl -sk -o /dev/null -w '%{http_code}' "$@" || true; }
expect() {
  local want=$1 what=$2
  shift 2
  local got
  got=$(code "$@")
  [[ "$got" == "$want" ]] || fail "$what: expected $want, got $got"
}

expect 308 "http:// redirected" http://127.0.0.1/
[[ $(curl -s -o /dev/null -w '%{redirect_url}' http://127.0.0.1/runs?x=1) == https://localhost/runs?x=1 ]] ||
  fail "http:// not redirected to the same path on https://localhost"
expect 200 "/ passed to the app, with no password" "$url/"
expect 404 "/a2a" "$url/a2a"
expect 404 "/.well-known/agent-card.json" "$url/.well-known/agent-card.json"
expect 413 "a body over 2 MB" \
  -H 'Content-Type: application/json' --data-binary @<(head -c 3000000 /dev/zero | tr '\0' a) \
  "$url/"
expect 200 "another host name, answered by this site and not the packaged one" -H 'Host: elsewhere.example' "$url/"
expect 000 "TLS 1.2" --tls-max 1.2 "$url/"
curl -sk -o /dev/null -D - "$url/" | grep -qi '^Strict-Transport-Security: max-age=63072000' ||
  fail "no HSTS header"

headers=$(curl -sk "$url/")
grep -qi '^X-Forwarded-Proto: https' <<<"$headers" || fail "X-Forwarded-Proto not passed to the app"
grep -qi '^X-Forwarded-For: 127.0.0.1' <<<"$headers" || fail "X-Forwarded-For not passed to the app"
grep -qi '^Host: 127.0.0.1' <<<"$headers" || fail "Host not passed to the app"
grep -q '^Upstream: 7860' <<<"$headers" || fail "port 443 does not reach the app"
if curl -s -H 'Host: elsewhere.example' http://127.0.0.1/ | grep -qi 'welcome to nginx'; then
  fail "the packaged default site still answers"
fi

# The workbench, on port 8443.
workbench=https://127.0.0.1:8443
expect 200 "8443 passed to the workbench, with no password" "$workbench/"
expect 404 "8443 /a2a" "$workbench/a2a"
expect 404 "8443 /.well-known/agent-card.json" "$workbench/.well-known/agent-card.json"
expect 000 "8443 TLS 1.2" --tls-max 1.2 "$workbench/"
expect 308 "http:// to 8443 redirected" http://127.0.0.1:8443/viewer/
[[ $(curl -s -o /dev/null -w '%{redirect_url}' http://127.0.0.1:8443/viewer/?x=1) == https://127.0.0.1:8443/viewer/?x=1 ]] ||
  fail "http:// to 8443 not redirected to the same path on https://"
curl -sk -o /dev/null -D - "$workbench/" | grep -qi '^Strict-Transport-Security: max-age=63072000' ||
  fail "no HSTS header on 8443"
headers=$(curl -sk "$workbench/")
grep -q '^Upstream: 8000' <<<"$headers" || fail "port 8443 does not reach the workbench"
grep -qi '^X-Forwarded-Proto: https' <<<"$headers" || fail "X-Forwarded-Proto not passed to the workbench"

[[ $status -eq 0 ]] && echo "nginx: every check passed"
exit "$status"
