"""Versioned prompts held in the repository (§5.4, C14).

§5.4 requires the prompt to live in the repository with a version number, recorded with each
run. A version string alone does not achieve that — if the file can be edited without the
version changing, an old run record points at text that no longer exists. So the manifest
carries the hash as well and a mismatch is a hard failure.

That makes editing a prompt a deliberate two-step act: write `v2.md`, point the manifest at it.
The old version stays on disk and an old run stays resolvable.

`langchain.hub` is deliberately not used. In LangChain v1 it moved to `langchain_classic.hub`,
which is a clear signal that hosted prompts are not the default, and a prototype whose whole
argument is auditability should not fetch its prompts over the network.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from standards_advisor.errors import PromptNotFound
from standards_advisor.ids import sha256_text
from standards_advisor.models.common import PromptRef

MANIFEST_NAME = "manifest.toml"


@dataclass(frozen=True)
class Prompt:
    """One prompt at one version, with the hash of the text actually loaded."""

    name: str
    version: str
    text: str
    sha256: str

    def ref(self) -> PromptRef:
        return PromptRef(name=self.name, version=self.version, sha256=self.sha256)


class PromptLibrary:
    """Loads prompts from a directory laid out as `<name>/<version>.md`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._manifest_path = root / MANIFEST_NAME
        self._entries = self._load_manifest()

    def _load_manifest(self) -> dict[str, dict[str, str]]:
        if not self._manifest_path.is_file():
            raise PromptNotFound(f"no prompt manifest at {self._manifest_path}")
        with self._manifest_path.open("rb") as handle:
            raw = tomllib.load(handle)
        entries: dict[str, dict[str, str]] = {}
        for name, value in raw.items():
            if not isinstance(value, dict):
                raise PromptNotFound(f"manifest entry {name!r} is not a table")
            missing = {"current", "sha256"} - value.keys()
            if missing:
                raise PromptNotFound(
                    f"manifest entry {name!r} is missing {', '.join(sorted(missing))}"
                )
            entries[name] = {"current": str(value["current"]), "sha256": str(value["sha256"])}
        return entries

    def names(self) -> list[str]:
        return sorted(self._entries)

    def get(self, name: str) -> Prompt:
        """Load the current version of `name`, verifying its hash.

        Raises `PromptNotFound` if the prompt is unknown, its file is absent, or its content no
        longer matches the hash the manifest records for it.
        """
        entry = self._entries.get(name)
        if entry is None:
            known = ", ".join(self.names()) or "none"
            raise PromptNotFound(f"prompt {name!r} is not in the manifest; known: {known}")

        version = entry["current"]
        path = self.root / name / f"{version}.md"
        if not path.is_file():
            raise PromptNotFound(f"prompt {name!r} version {version} not found at {path}")

        text = path.read_text(encoding="utf-8")
        digest = sha256_text(text)
        if digest != entry["sha256"]:
            raise PromptNotFound(
                f"prompt {name!r} version {version} has hash {digest} but the manifest records "
                f"{entry['sha256']}; write a new version rather than editing this one, then "
                f"update {MANIFEST_NAME}"
            )
        return Prompt(name=name, version=version, text=text, sha256=digest)
