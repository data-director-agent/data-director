"""Write a pure Python wheel of the packages in a folder, the same bytes each time (build.ts).

    python -I write_wheel.py FOLDER NAME VERSION OUT

Used for the stand-in for spaCy (`spacy-stub/`), which is not a project of its own. Prints the
wheel's file name.
"""

from __future__ import annotations

import base64
import hashlib
import sys
import zipfile
from pathlib import Path


def _digest(data: bytes) -> str:
    raw = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
    return f"sha256={raw}"


def write_wheel(source: Path, name: str, version: str, out: Path) -> Path:
    stem = f"{name.replace('-', '_')}-{version}"
    info = f"{stem}.dist-info"
    files = {
        p.relative_to(source).as_posix(): p.read_bytes()
        for p in sorted(source.rglob("*.py"))
        if "__pycache__" not in p.parts
    }
    files[f"{info}/METADATA"] = (
        f"Metadata-Version: 2.4\nName: {name}\nVersion: {version}\nLicense-Expression: MIT\n"
        "Summary: The names Presidio imports from spaCy and thinc, for the browser bundle\n"
    ).encode()
    files[f"{info}/WHEEL"] = (
        b"Wheel-Version: 1.0\nGenerator: dd-inventory bundle\nRoot-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    record = [f"{path},{_digest(data)},{len(data)}" for path, data in files.items()]
    files[f"{info}/RECORD"] = ("\n".join([*record, f"{info}/RECORD,,"]) + "\n").encode()
    wheel = out / f"{stem}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w", zipfile.ZIP_DEFLATED) as z:
        for path, data in files.items():
            z.writestr(zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0)), data)
    return wheel


if __name__ == "__main__":
    source, name, version, out = sys.argv[1:5]
    sys.stdout.write(write_wheel(Path(source), name, version, Path(out)).name + "\n")
