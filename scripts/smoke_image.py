"""Smoke test for the published image (docker/release.Dockerfile, #223).

Starts `docker/compose.image.yaml` (every agent and the app, each a container of the one image),
waits until every agent serves its card and the app answers `/api/agents`, then checks that the
app reaches every agent the stack runs, finds none incompatible, serves the shell and the browser
scanner's bundle, and reports the commit the image was built from. It always stops the stack and removes its volumes.

    python3 scripts/smoke_image.py --image data-director:test --revision "$(git rev-parse HEAD)"

Docker with Compose is all it needs: no checkout packages, no uv. It exits 1, after printing the
containers' logs, if any check fails. It is not a test of conformance; scripts/smoke_agents.py
exercises the agents' behaviour from a checkout.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request
from email.message import Message
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker/compose.image.yaml"
PROJECT = "dd-image-smoke"
WAIT_TIMEOUT_S = 300
# Whom the app's runs act for; the app will not start without a principal or sign-in.
PRINCIPAL = {"DD_PRINCIPAL_ID": "https://orcid.org/0000-0002-1825-0097", "DD_PRINCIPAL_NAME": "CI"}


class SmokeError(Exception):
    """A check that did not hold."""


def compose(env: dict[str, str], *args: str, capture: bool = False) -> str:
    done = subprocess.run(
        ["docker", "compose", "--project-name", PROJECT, "--file", str(COMPOSE), *args],
        env=env,
        check=True,
        text=True,
        capture_output=capture,
    )
    return done.stdout if capture else ""


# The browser scanner's bundle (inventory/browser/README.md): the app offers Describe a folder in
# this browser exactly when it serves the manifest (app/web/src/scan/scanner.ts).
BUNDLE = "inventory-bundle"
BUNDLE_WASM = "pyodide.asm.wasm"
BUNDLE_CACHING = "no-cache"


def fetch(url: str) -> tuple[Message, bytes]:
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.headers, response.read()


def get(url: str) -> tuple[str, bytes]:
    headers, body = fetch(url)
    return headers.get_content_type(), body


def get_json(url: str) -> Any:
    _, body = get(url)
    return json.loads(body)


def check_bundle(base: str) -> None:
    """Raise SmokeError unless the app serves the scanner's bundle as a browser needs it."""
    headers, body = fetch(f"{base}/{BUNDLE}/manifest.json")
    manifest = json.loads(body)
    if not (manifest.get("pyodide") and manifest.get("wheels") and manifest.get("files")):
        raise SmokeError(f"/{BUNDLE}/manifest.json names no Pyodide, wheels or files")
    if headers.get("cache-control") != BUNDLE_CACHING:
        raise SmokeError(f"/{BUNDLE}/ is sent Cache-Control {headers.get('cache-control')!r}")
    for path in manifest["files"]:
        fetch(f"{base}/{BUNDLE}/{path}")
    kind, _ = get(f"{base}/{BUNDLE}/{BUNDLE_WASM}")
    if kind != "application/wasm":
        raise SmokeError(f"/{BUNDLE}/{BUNDLE_WASM} is served as {kind}")
    notices = manifest.get("notices")
    if not notices or not get(f"{base}/{BUNDLE}/{notices}")[1]:
        raise SmokeError(f"/{BUNDLE}/ serves no licence notices")


def check(base: str, agents: set[str], revision: str | None) -> None:
    """Raise SmokeError on the first thing the running stack gets wrong."""
    about = get_json(f"{base}/api/about")
    if missing := agents & set(about.get("unavailable") or []):
        raise SmokeError(f"the app cannot reach {sorted(missing)}, which the stack runs")
    if incompatible := about.get("incompatible"):
        raise SmokeError(f"the app finds {incompatible} incompatible")
    if revision and about.get("commit") != revision:
        raise SmokeError(f"the app reports commit {about.get('commit')!r}, not {revision!r}")
    listed = get_json(f"{base}/api/agents").get("agents") or []
    if len(listed) < len(agents):
        raise SmokeError(f"/api/agents lists {len(listed)} agents; the stack runs {len(agents)}")
    kind, body = get(f"{base}/")
    if kind != "text/html" or b"<html" not in body.lower():
        raise SmokeError(f"/ serves {kind}, not the shell")
    check_bundle(base)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--image", required=True, help="the image to start, as name:tag or name@digest"
    )
    parser.add_argument("--revision", help="the commit the app must report (GET /api/about)")
    parser.add_argument("--port", type=int, default=7860, help="the app's port on loopback")
    args = parser.parse_args(argv)

    env = {**os.environ, **PRINCIPAL, "DD_IMAGE": args.image, "DD_APP_HOST_PORT": str(args.port)}
    # The services the stack starts, without opt-in profiles: the app and the agents it must reach.
    services = set(compose(env, "config", "--services", capture=True).split())
    agents = services - {"app"}
    try:
        compose(env, "up", "--detach", "--wait", "--wait-timeout", str(WAIT_TIMEOUT_S))
        check(f"http://127.0.0.1:{args.port}", agents, args.revision)
    except (SmokeError, subprocess.CalledProcessError, OSError, ValueError) as error:
        print(f"smoke_image: {error}", file=sys.stderr)
        subprocess.run(
            ["docker", "compose", "--project-name", PROJECT, "--file", str(COMPOSE), "logs"],
            env=env,
            check=False,
        )
        return 1
    finally:
        compose(env, "down", "--volumes", "--remove-orphans")
    print(f"smoke_image: {args.image} ran {len(agents)} agents and the app")
    return 0


if __name__ == "__main__":
    sys.exit(main())
