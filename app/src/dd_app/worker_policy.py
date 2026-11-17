"""The browser scanner's worker runs under its own Content Security Policy (docs/specs/app.md).

The scanner (`@data-director/inventory`, README.md, Browser scanner) runs `dd-inventory` under
Pyodide in a Web Worker over a folder the researcher chooses. The page fetches the scanner's
bundle from `/inventory-bundle/` and hands it in, so the worker needs no network: its script is
sent `connect-src 'none'`, and may run only the `blob:` scripts it makes of the bundle and
WebAssembly. A worker takes its policy from the response that delivers its script, so the policy
is set here, on that one path, whoever stands in front of the app.

The shell's build names the worker's script `assets/inventory-scanner-<hash>.js`
(`app/web/vite.config.ts`, which sends the same policy in preview).
"""

from __future__ import annotations

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

WORKER_POLICY = "default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'"
WORKER_PATH = re.compile(r"/assets/inventory-scanner-[^/]*\.js")


class WorkerPolicy:
    """ASGI middleware: the worker's policy on its script's response, and nothing else changed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not WORKER_PATH.fullmatch(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def send_with_policy(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v)
                    for k, v in message.get("headers", [])
                    if k.lower() != b"content-security-policy"
                ]
                headers.append((b"content-security-policy", WORKER_POLICY.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_policy)
