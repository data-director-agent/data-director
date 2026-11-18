"""`dd-vendor-skill`: vendor an Agent Skill into an agent's package from a release of the
`skills` repository, and pin it (`dd_sdk.skills`, docs/specs/agents.md).

    uv run dd-vendor-skill skills-v1.2.0.tar.gz --skill licence-choice --version v1.2.0 \\
        --source https://github.com/.../releases/tag/v1.2.0 \\
        --into agents/advisor-rights/src/dd_agent_advisor_rights/skills

The release is a directory or a `.tar.gz`, `.tgz` or `.zip` archive already on disk: the command
reads no network, so what is vendored is what the person downloaded and can inspect. It finds the
directory named for the Skill that holds a `SKILL.md`, refuses it as `load_skill` would (anything
but text, a front matter naming another Skill), replaces the vendored copy and writes the new
version, source and digest to `pins.json`. A refused release leaves the vendored copy as it was.
The change is then reviewed as a prompt change.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Sequence
from pathlib import Path

from dd_sdk.skills import (
    PINS,
    SKILL_FILE,
    SkillError,
    SkillUse,
    load_skill,
    read_pins,
    skill_digest,
    skill_files,
)


def vendor(release: Path, name: str, version: str, source: str, into: Path) -> SkillUse:
    """Vendor the Skill `name` from `release` into `into`, pin it and return the pin."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _unpack(release, Path(tmp))
        found = _find(root, name)
        skill_files(found)  # refuses scripts and anything else before the copy is touched
        staged = Path(tmp) / "staged" / name
        staged.parent.mkdir()
        # Contents only: no file mode or link is carried over from the release.
        for path in skill_files(found):
            target = staged / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((found / path).read_bytes())
        try:
            use = SkillUse(name, version, skill_digest(staged))
        except ValueError as exc:
            raise SkillError(str(exc)) from exc
        pin = {"version": version, "source": source, "sha256": use.sha256}
        # Loaded as an agent would load it, before the vendored copy is touched.
        _write_pins(staged.parent, {name: pin})
        load_skill(staged.parent, name)
        into.mkdir(parents=True, exist_ok=True)
        pins = read_pins(into)
        shutil.rmtree(into / name, ignore_errors=True)
        shutil.copytree(staged, into / name)
        pins[name] = pin
        _write_pins(into, pins)
    return use


def _write_pins(into: Path, pins: dict[str, dict[str, str]]) -> None:
    text = json.dumps(dict(sorted(pins.items())), indent=2, sort_keys=True) + "\n"
    (into / PINS).write_text(text, encoding="utf-8")


def _unpack(release: Path, tmp: Path) -> Path:
    if release.is_dir():
        return release
    out = tmp / "release"
    if release.name.endswith((".tar.gz", ".tgz")):
        with tarfile.open(release) as archive:
            archive.extractall(out, filter="data")
    elif release.suffix == ".zip":
        with zipfile.ZipFile(release) as archive:
            archive.extractall(out)
    else:
        raise SkillError(f"{release} is not a directory, .tar.gz, .tgz or .zip")
    return out


def _find(root: Path, name: str) -> Path:
    found = sorted(p.parent for p in root.rglob(SKILL_FILE) if p.parent.name == name)
    if len(found) != 1:
        raise SkillError(
            f"{root} holds {len(found)} directories named {name!r} with a {SKILL_FILE}; "
            "expected exactly one"
        )
    return found[0]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="dd-vendor-skill",
        description="Vendor an Agent Skill from a release into an agent's package, and pin it.",
    )
    parser.add_argument("release", type=Path, help="the release: a directory or an archive")
    parser.add_argument("--skill", required=True, help="the Skill's name")
    parser.add_argument("--version", required=True, help="the release's version, such as v1.2.0")
    parser.add_argument("--source", required=True, help="where the release was published")
    parser.add_argument("--into", required=True, type=Path, help="the agent package's skills/")
    args = parser.parse_args(argv)
    try:
        use = vendor(args.release, args.skill, args.version, args.source, args.into)
    except SkillError as exc:
        sys.stderr.write(f"dd-vendor-skill: {exc}\n")
        return 1
    sys.stdout.write(f"{use.name} {use.version} sha256 {use.sha256}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
