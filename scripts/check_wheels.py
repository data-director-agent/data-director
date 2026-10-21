"""Check that each built wheel installs on its own and imports.

The uv workspace installs every member together, so a package that imports a library it does not
declare still passes the test suite. This script installs each wheel in `DIST` into a fresh
virtual environment, with only what the wheel declares (other workspace members are found among
the wheels beside it), and imports every top-level package the wheel contains.

    uv build --all-packages -o dist && uv run python scripts/check_wheels.py dist

It exits 1 if any wheel fails to install or import, after checking every wheel.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def top_level_packages(wheel: Path) -> list[str]:
    """The importable packages at the root of `wheel`."""
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
    return sorted(
        {n.split("/", 1)[0] for n in names if n.count("/") == 1 and n.endswith("/__init__.py")}
    )


def check(wheel: Path, dist: Path, uv: str) -> str | None:
    """None if `wheel` installs alone and its packages import, else what went wrong."""
    packages = top_level_packages(wheel)
    if not packages:
        return "contains no package"
    with tempfile.TemporaryDirectory(prefix="dd-wheel-") as tmp:
        venv = Path(tmp) / "venv"
        python = venv / "bin" / "python"
        # The interpreter running this script, so the wheel's requires-python is honoured.
        steps = [
            [uv, "venv", "--quiet", "--python", sys.executable, str(venv)],
            [uv, "pip", "install", "--quiet", "--python", str(python),
             "--find-links", str(dist), str(wheel)],
            [str(python), "-c", "; ".join(f"import {p}" for p in packages)],
        ]  # fmt: skip
        for step in steps:
            run = subprocess.run(step, capture_output=True, text=True, check=False)
            if run.returncode != 0:
                return f"`{' '.join(step[:3])} …` failed:\n{run.stderr.strip()}"
    return None


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    dist = Path(argv[0]).resolve()
    wheels = sorted(dist.glob("*.whl"))
    uv = shutil.which("uv")
    if not wheels or uv is None:
        print(f"no wheels in {dist}" if not wheels else "uv is not on PATH", file=sys.stderr)
        return 2
    failed = 0
    for wheel in wheels:
        problem = check(wheel, dist, uv)
        print(
            f"{'FAIL' if problem else 'ok'}    {wheel.name}" + (f"\n{problem}" if problem else "")
        )
        failed += problem is not None
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
