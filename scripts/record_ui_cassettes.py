"""Record the AG-UI cassettes the app's shell replays (`app/web/cassettes/*.jsonl`).

Each cassette is what the harness's AG-UI binding streams for one kind of run (docs/specs/transport.md),
made with the agents in process and with ids and times held fixed. The recording is a test,
`app/tests/test_ui_cassettes.py`, which in CI fails on a cassette that has fallen behind; this script
runs it with rewriting on, so a developer can refresh every cassette and commit what changed:

    uv run python scripts/record_ui_cassettes.py

A local `uv run pytest` rewrites stale cassettes too, as it does the fixtures in `app/web/fixtures`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST = "app/tests/test_ui_cassettes.py"


def main() -> int:
    env = {**os.environ, "DD_WRITE_FIXTURES": "1"}
    command = [sys.executable, "-m", "pytest", TEST, "-q", "-p", "no:randomly"]
    return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
