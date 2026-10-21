"""End-to-end smoke test: every agent as a separate service, reached over real HTTP.

The test suite serves agents in memory (`dd_harness.testing.in_process`); this script runs what a
developer runs instead. It starts every agent with `scripts/run-agents.sh` and `workbench serve`,
then checks that each agent registers, that each sample in `workbench/samples/README.md` reaches
the outcome it is documented to reach through `workbench invoke`, that `workbench verify` passes
on each envelope, and that the orchestrator delegates over AG-UI. Runs are written to a temporary
directory, never to `workbench/runs/`.

    uv run python scripts/smoke_agents.py

It exits 1 on the first check that fails, after stopping every process it started. It carries no
requirement marker and is not a test of conformance: it shows that the parts run together.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKBENCH = ROOT / "workbench"
SAMPLES = WORKBENCH / "samples"
# How long a service may take to answer for the first time: `uv run` may build the package.
START_TIMEOUT_S = 120
WORKBENCH_PORT = 8100
PRINCIPAL = {"DD_PRINCIPAL_ID": "https://orcid.org/0000-0002-1825-0097", "DD_PRINCIPAL_NAME": "CI"}

# (agent, sample, outcome.status), as samples/README.md documents them.
CASES = [
    ("hello.world", "hello.salutation.json", "succeeded"),
    ("quality.reviewer", "orda-record.metadata.json", "succeeded"),
    ("fact.checker", "claim.json", "succeeded"),
    ("standards.advisor", "soil-chemistry.profile.json", "succeeded"),
    ("standards.advisor", "empty.profile.json", "abstained"),
    ("quality.reviewer", "claim.json", "failed"),
]


class SmokeError(Exception):
    """A check that did not hold."""


def check(condition: bool, message: str, detail: object = "") -> None:
    """Print `message` if `condition` holds; otherwise fail with `detail` appended."""
    if not condition:
        raise SmokeError(f"{message}\n{detail}" if detail else message)
    print(f"ok    {message}")


@contextmanager
def started(cmd: list[str], env: dict[str, str], log: Path) -> Iterator[None]:
    """Run `cmd` in its own process group for the duration, and stop the whole group after."""
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(
            cmd, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, start_new_session=True
        )
        try:
            yield
        finally:
            with suppress(ProcessLookupError):
                os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                with suppress(ProcessLookupError):
                    os.killpg(proc.pid, signal.SIGKILL)


def wait_for(url: str, log: Path) -> None:
    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return
        except urllib.error.URLError, ConnectionError, TimeoutError:
            time.sleep(0.5)
    raise SmokeError(f"{url} did not answer in {START_TIMEOUT_S}s\n{log.read_text()}")


def workbench(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    exe = shutil.which("workbench")
    if exe is None:
        raise SmokeError("`workbench` is not on PATH; run this with `uv run`")
    return subprocess.run(
        [exe, *args], cwd=WORKBENCH, env=env, capture_output=True, text=True, check=False
    )


def agui_run(agent_id: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """One AG-UI run against `workbench serve`, as the viewer's `postRun` sends it."""
    invocation_id = str(uuid.uuid7())
    request = {
        "agent_id": agent_id,
        "input": payload,
        "invocation_id": invocation_id,
        "issued_at": datetime.now(UTC).isoformat(),
        "requirement_ids": [],
    }
    body = {
        "threadId": "smoke",
        "runId": invocation_id,
        "messages": [],
        "state": {},
        "tools": [],
        "context": [],
        "forwardedProps": {"request": request},
    }
    req = urllib.request.Request(
        f"http://127.0.0.1:{WORKBENCH_PORT}/agui",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json", "accept": "text/event-stream"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        text = resp.read().decode()
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def smoke(tmp: Path) -> None:
    env = {**os.environ, **PRINCIPAL, "DD_RUNS_DIR": str(tmp / "runs")}
    agents_log, serve_log = tmp / "agents.log", tmp / "serve.log"
    urls = [e["url"] for e in yaml.safe_load((WORKBENCH / "agents.yaml").read_text())["agents"]]

    with started([str(ROOT / "scripts" / "run-agents.sh")], env, agents_log):
        for url in urls:
            wait_for(f"{url}/.well-known/agent-card.json", agents_log)
        check(True, f"{len(urls)} agent services answer")

        listed = workbench(env, "agents", "--json")
        check(listed.returncode == 0, "`workbench agents` exits 0", listed.stderr)
        listing = json.loads(listed.stdout)
        check(
            not listing["unavailable"] and not listing["incompatible"],
            "every agent registers",
            {k: listing[k] for k in ("unavailable", "incompatible")},
        )

        for agent, sample, status in CASES:
            run = workbench(env, "invoke", "--agent", agent, "--input", str(SAMPLES / sample))
            check(run.returncode == 0, f"invoke {agent} on {sample} exits 0", run.stderr)
            envelope = json.loads(run.stdout)
            got = envelope["outcome"]["status"]
            check(got == status, f"{agent} on {sample} is {status}", f"got {got}")
            path = tmp / f"{envelope['invocation_id']}.json"
            path.write_text(run.stdout, encoding="utf-8")
            verified = workbench(env, "verify", str(path))
            check(verified.returncode == 0, f"verify {agent} on {sample}", verified.stdout)

        serve = [str(shutil.which("workbench")), "serve", "--port", str(WORKBENCH_PORT)]
        with started(serve, {**env, "PWD": str(WORKBENCH)}, serve_log):
            wait_for(f"http://127.0.0.1:{WORKBENCH_PORT}/agents", serve_log)
            message = json.loads((SAMPLES / "director.message.json").read_text())
            events = agui_run("director.stub", message)
            finished = [e for e in events if e["type"] == "RUN_FINISHED"]
            check(len(finished) == 1, "AG-UI run of director.stub finishes", events)
            envelope = finished[0]["result"]
            check(
                envelope["outcome"]["status"] == "succeeded",
                "director.stub succeeds over AG-UI",
                envelope["outcome"],
            )
            check(
                bool(envelope.get("delegations")),
                "director.stub's envelope records a delegation",
            )


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="dd-smoke-") as tmp:
        try:
            smoke(Path(tmp))
        except SmokeError as exc:
            print(f"FAIL  {exc}", file=sys.stderr)
            for log in sorted(Path(tmp).glob("*.log")):
                print(f"--- {log.name}\n{log.read_text()}", file=sys.stderr)
            return 1
    print("smoke test passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
