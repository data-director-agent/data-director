"""Fixtures for the viewer's browser tests: the workbench app on a real socket, and the viewer's
CDN modules replayed from a recorded HAR.

The agents are served in memory, as in `workbench/tests/`; only the page reaches the app over
HTTP, because a browser cannot use an ASGI transport. The viewer loads React and RJSF from
`esm.sh`; the tests replay those responses from `esm.sh.har.zip` and abort every other request
that leaves the machine, so no test reaches the network. After changing a pinned module in
`viewer/js/`, re-record the HAR (this does reach `esm.sh`):

    uv run pytest workbench/browser_tests --update-har
"""

from __future__ import annotations

import re
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, ConsoleMessage, Error, Page, Route

from dd_agent_director.agent import build as build_director
from dd_agent_factcheck.agent import FactChecker
from dd_agent_hello.agent import HelloWorld
from dd_agent_quality.agent import QualityReviewer
from dd_agent_stub.agent import AbstainingStub
from dd_harness.identity import OperatorAssertion
from dd_harness.testing import TEST_PRINCIPAL, make_conductor
from workbench.transport.app import build_app

HAR = Path(__file__).with_name("esm.sh.har.zip")
CDN = "https://esm.sh/**"
# Anything but the app itself.
REMOTE = re.compile(r"^(?!http://127\.0\.0\.1:\d+/)")
PAGES = ("/viewer/", "/viewer/chat.html", "/viewer/agents.html")
START_TIMEOUT_S = 10


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-har",
        action="store_true",
        help="re-record the viewer's esm.sh modules into esm.sh.har.zip (reaches the network)",
    )


@pytest.fixture(scope="session")
def server_url(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """The workbench app over every in-memory agent a viewer test uses, on an ephemeral port.

    The conductor is built on the server's own thread: Playwright's sync API keeps an event loop
    running on the test thread, and the conductor's `asyncio.run` cannot run inside it.
    """
    runs_dir = tmp_path_factory.mktemp("runs")
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    url = f"http://127.0.0.1:{sock.getsockname()[1]}"
    servers: list[uvicorn.Server] = []

    def serve() -> None:
        conductor = make_conductor(
            runs_dir,
            HelloWorld(),
            AbstainingStub(),
            QualityReviewer(),
            FactChecker(),
            build_director(),
        )
        app = build_app(conductor, OperatorAssertion(TEST_PRINCIPAL), base_url=url)
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", lifespan="off"))
        servers.append(server)
        server.run(sockets=[sock])

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    deadline = time.monotonic() + START_TIMEOUT_S
    while not (servers and servers[0].started):
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("the workbench app did not start")
        time.sleep(0.05)
    yield url
    servers[0].should_exit = True
    thread.join(timeout=START_TIMEOUT_S)
    sock.close()


@pytest.fixture(scope="session")
def recorded_har(
    request: pytest.FixtureRequest, browser: Browser, server_url: str
) -> Iterator[Path]:
    """The HAR the tests replay, re-recorded first from every page if `--update-har` is given."""
    if request.config.getoption("--update-har"):
        context = browser.new_context()
        context.route_from_har(HAR, url=CDN, update=True, update_content="embed")
        page = context.new_page()
        for path in PAGES:
            page.goto(server_url + path)
            page.wait_for_load_state("networkidle")
        context.close()  # the HAR is written when its context closes
    if not HAR.is_file():
        pytest.fail(f"{HAR.name} is missing; record it with --update-har")
    yield HAR


@pytest.fixture
def page_errors() -> list[str]:
    """What went wrong on the `viewer` page. A test that expects an error removes it."""
    return []


@pytest.fixture
def viewer(
    page: Page, server_url: str, recorded_har: Path, page_errors: list[str]
) -> Iterator[Page]:
    """A page that can reach only the app and the recorded CDN modules, and that fails the test
    on any script error, console error or blocked request."""
    errors = page_errors

    def abort(route: Route) -> None:
        errors.append(f"blocked request to {route.request.url}")
        route.abort()

    def console(msg: ConsoleMessage) -> None:
        if msg.type == "error":
            errors.append(f"console: {msg.text}")

    def page_error(exc: Error) -> None:
        errors.append(f"page error: {exc}")

    # A route registered later is tried first: the HAR for esm.sh, then the catch-all.
    page.route(REMOTE, abort)
    page.route_from_har(recorded_har, url=CDN, not_found="abort")
    page.on("console", console)
    page.on("pageerror", page_error)
    yield page
    assert not errors, "\n".join(errors)
