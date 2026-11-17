"""The headers the browser scanner's assets need, whoever serves the app (docs/specs/app.md).

The worker runs under its own Content Security Policy, and the bundle is revalidated on every use.

The scanner (`@data-director/inventory`, README.md, Browser scanner) runs `dd-inventory` under
Pyodide in a Web Worker over a folder the researcher chooses. The page fetches the scanner's
bundle from `/inventory-bundle/` and hands it in, so the worker needs no network: its script is
sent `connect-src 'none'`, and may run only the `blob:` scripts it makes of the bundle and
WebAssembly. A worker takes its policy from the response that delivers its script, so the policy
is set here, on that one path, whoever stands in front of the app.

The shell's build names the worker's script `assets/inventory-scanner-<hash>.js`
(`app/web/vite.config.ts`, which sends the same policy in preview).

Most of the bundle's file names stay the same from one release to the next (`manifest.json`,
`pyodide-lock.json`, `pyodide.asm.wasm`, and the command's wheel while its version does), so a
browser left to cache them by heuristic could pair one release's lock with another's wheel, whose
digest would then not match. Every file under `/inventory-bundle/` is sent `Cache-Control:
no-cache`: the browser keeps its copy and asks with the ETag whether it still holds, so a scan
fetches the bundle again only after a deployment has changed it.
"""

from __future__ import annotations

import re

from starlette.types import ASGIApp, Message, Receive, Scope, Send

WORKER_POLICY = "default-src 'none'; script-src blob: 'wasm-unsafe-eval'; connect-src 'none'"
WORKER_PATH = re.compile(r"/assets/inventory-scanner-[^/]*\.js")
BUNDLE_CACHING = "no-cache"
BUNDLE_PREFIX = "/inventory-bundle/"


def _with_header(message: Message, name: bytes, value: str) -> Message:
    """`message`, if it starts the response, with `name` set to `value` in place of any it had."""
    if message["type"] != "http.response.start":
        return message
    headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != name]
    headers.append((name, value.encode()))
    return {**message, "headers": headers}


class _HeaderOnPath:
    """ASGI middleware: one header set on the responses to the paths `applies_to` accepts."""

    header: bytes
    value: str

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    @staticmethod
    def applies_to(path: str) -> bool:
        raise NotImplementedError

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.applies_to(scope["path"]):
            await self.app(scope, receive, send)
            return

        async def send_with_header(message: Message) -> None:
            await send(_with_header(message, self.header, self.value))

        await self.app(scope, receive, send_with_header)


class WorkerPolicy(_HeaderOnPath):
    """ASGI middleware: the worker's policy on its script's response, and nothing else changed."""

    header = b"content-security-policy"
    value = WORKER_POLICY

    @staticmethod
    def applies_to(path: str) -> bool:
        return WORKER_PATH.fullmatch(path) is not None


class BundleCaching(_HeaderOnPath):
    """ASGI middleware: `Cache-Control: no-cache` on the bundle, and nothing else changed."""

    header = b"cache-control"
    value = BUNDLE_CACHING

    @staticmethod
    def applies_to(path: str) -> bool:
        return path.startswith(BUNDLE_PREFIX)
