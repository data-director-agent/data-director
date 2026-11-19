"""Agent Skills a persona loads into its system prompt (docs/specs/agents.md, Tools: MCP servers
and Agent Skills).

A Skill is procedural know-how written once in the `skills` repository and vendored into an
agent's package at a pinned release, beside `system_prompt.md`:

    dd_agent_<name>/
      system_prompt.md
      skills/
        pins.json            {"<skill>": {"version": ..., "source": ..., "sha256": ...}}
        <skill>/SKILL.md     front matter (name, description), then the procedure
        <skill>/references/  optional text the procedure relies on

Code chooses which Skills a step needs, with `load_skills`, and puts their text into the system
prompt with `with_skills`; the model never chooses a Skill and has no filesystem to read one. The
prompt digest (`dd_sdk.prompts`) then covers the Skill's text, so nothing else is recorded per
call. The agent's card declares each Skill it may load, as a `SkillUse` taken from the loaded
Skill, so the card and the text sent cannot disagree.

A Skill a persona loads is text only: `SKILL.md` and Markdown or plain-text files under
`references/`. A script, an asset or anything else is refused, since an exact procedure belongs
in the agent's deterministic shell or on an MCP server. A Skill whose files do not hash to its pin
is refused too, so an edit to a vendored copy cannot reach a prompt unreviewed. Both refusals are
configuration errors, raised as `SkillError`.

A Skill's digest is `dd-skill-files-v1`: SHA-256 over one line per file, sorted by path,
`<SHA-256 of the file's bytes>  <path relative to the Skill, with />` and a newline, as
`sha256sum` prints them. Like the prompt digest it is not an evidence canonicalisation
(`dd_sdk.evidence`): it names what the agent was told, not what a claim rests on.

`dd-vendor-skill` (`dd_sdk.skills_vendor`) refreshes a vendored Skill from a release.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

SKILL_DIGEST = "dd-skill-files-v1"
PINS = "pins.json"
SKILL_FILE = "SKILL.md"
REFERENCES = "references"
TEXT_SUFFIXES = frozenset({".md", ".txt"})

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# A Skill's name as the Agent Skills format allows it: lower-case letters, digits and hyphens.
_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SkillError(Exception):
    """A vendored Skill cannot be loaded as pinned. The message says what to do."""


@dataclass(frozen=True)
class SkillUse:
    """A Skill an agent may load, as its card declares it: name, pinned release and digest."""

    name: str
    version: str
    sha256: str

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise ValueError(f"skill name {self.name!r}: expected lower-case words and hyphens")
        if not self.version:
            raise ValueError(f"skill {self.name!r} names no version")
        if not _SHA256.match(self.sha256):
            raise ValueError(f"skill {self.name!r}: sha256 {self.sha256!r} is not 64 hex digits")

    def describe(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version, "sha256": self.sha256}


@dataclass(frozen=True)
class Skill:
    """A Skill loaded as pinned: what the card declares, and the text for the system prompt."""

    use: SkillUse
    text: str


def skill_files(directory: Path) -> list[PurePosixPath]:
    """Every file in a Skill, relative to it, sorted; a `SkillError` if any is not text the
    persona may load, or `SKILL.md` is missing."""
    found = sorted(
        PurePosixPath(p.relative_to(directory).as_posix())
        for p in directory.rglob("*")
        if p.is_file() or p.is_symlink()
    )
    refused = [str(p) for p in found if not _loadable(directory, p)]
    if refused:
        raise SkillError(
            f"skill {directory.name!r} carries {refused}; a Skill a persona loads holds only "
            f"{SKILL_FILE} and Markdown or text under {REFERENCES}/, so make a script code in the "
            "agent or a tool on an MCP server (docs/specs/agents.md)"
        )
    if PurePosixPath(SKILL_FILE) not in found:
        raise SkillError(f"skill {directory.name!r} has no {SKILL_FILE}")
    return found


def _loadable(directory: Path, path: PurePosixPath) -> bool:
    full = directory / path
    if full.is_symlink() or full.stat().st_mode & 0o111:
        return False
    if path == PurePosixPath(SKILL_FILE):
        return True
    return path.parts[0] == REFERENCES and path.suffix in TEXT_SUFFIXES


def skill_digest(directory: Path) -> str:
    """The `dd-skill-files-v1` digest of the Skill in `directory`."""
    lines = "".join(
        f"{hashlib.sha256((directory / p).read_bytes()).hexdigest()}  {p}\n"
        for p in skill_files(directory)
    )
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def read_pins(skills_dir: Path) -> dict[str, dict[str, str]]:
    """The pins in `skills_dir/pins.json`: each Skill's version, source and digest, by name. None
    yet: empty."""
    path = skills_dir / PINS
    if not path.exists():
        return {}
    try:
        pins = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SkillError(f"{path} is not JSON: {exc}") from exc
    if not isinstance(pins, dict) or not all(isinstance(v, dict) for v in pins.values()):
        raise SkillError(f"{path} must map each Skill's name to its version, source and sha256")
    return pins


def load_skill(skills_dir: Path, name: str) -> Skill:
    """The Skill `name`, vendored in `skills_dir`, checked against its pin."""
    pin = read_pins(skills_dir).get(name)
    if pin is None:
        raise SkillError(
            f"skill {name!r} is not pinned in {skills_dir / PINS}; vendor it with dd-vendor-skill"
        )
    directory = skills_dir / name
    if not directory.is_dir():
        raise SkillError(f"skill {name!r} is pinned but {directory} does not exist")
    try:
        use = SkillUse(name, str(pin.get("version", "")), str(pin.get("sha256", "")))
    except ValueError as exc:
        raise SkillError(f"{skills_dir / PINS}: {exc}") from exc
    digest = skill_digest(directory)
    if digest != use.sha256:
        raise SkillError(
            f"skill {name!r} hashes to {digest}, not the {use.sha256} pinned for {use.version}; "
            "a vendored Skill is changed only by vendoring a release with dd-vendor-skill"
        )
    return Skill(use, _text(directory, name))


def load_skills(skills_dir: Path, *names: str) -> tuple[Skill, ...]:
    """The Skills `names`, in that order, each checked against its pin."""
    return tuple(load_skill(skills_dir, name) for name in names)


def with_skills(system_prompt: str, skills: Iterable[Skill]) -> str:
    """`system_prompt` followed by each Skill's text under a heading naming it and its version."""
    parts = [system_prompt.rstrip()]
    parts.extend(f"## Skill: {s.use.name} ({s.use.version})\n\n{s.text}" for s in skills)
    return "\n\n".join(parts)


def _text(directory: Path, name: str) -> str:
    """`SKILL.md` without its front matter, then each reference under a heading naming its
    path: the model cannot follow a link to a file, so what the procedure relies on comes with
    it."""
    front, body = split_front_matter((directory / SKILL_FILE).read_text(encoding="utf-8"))
    if front.get("name") != name:
        raise SkillError(
            f"skill {name!r}: its {SKILL_FILE} names itself {front.get('name')!r}; the directory "
            "and the front matter's name must agree"
        )
    parts = [body.strip()]
    for path in skill_files(directory):
        if path.parts[0] == REFERENCES:
            parts.append(f"### {path}\n\n{(directory / path).read_text(encoding='utf-8').strip()}")
    return "\n\n".join(parts)


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """A `SKILL.md`'s front matter, as its top-level `key: value` lines, and the body after it.

    Only the top-level scalar keys are read (`name`, `description`, `license`); nested keys such
    as `metadata` are skipped, so no YAML parser is needed. No front matter: an empty mapping.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = next(i for i, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise SkillError(f"{SKILL_FILE}'s front matter is not closed with ---") from exc
    front: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if sep and key and not key[0].isspace():
            front[key.strip()] = value.strip().strip("\"'")
    return front, "\n".join(lines[end + 1 :])


def skills_from_description(agent_id: str, entry: Mapping[str, Any]) -> tuple[SkillUse, ...]:
    """The Skills a card declares. They may be absent: a card written before Skills could be
    loaded declares none. A malformed entry is a `ValueError` naming the agent."""
    declared: Sequence[Any] = entry.get("skills") or ()
    try:
        uses = tuple(
            SkillUse(str(s["name"]), str(s["version"]), str(s["sha256"])) for s in declared
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"agent {agent_id!r}: malformed skills: {exc}") from exc
    return uses
