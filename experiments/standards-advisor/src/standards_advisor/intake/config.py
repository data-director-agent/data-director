"""Loading and validating the versioned intake question set (§8).

Mirrors `ranking.weights` deliberately, down to the filename-is-the-version check: two
configuration loaders that behave differently is one more thing for a maintainer to hold in
their head, and the discipline being enforced is identical.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from standards_advisor.errors import ConfigError
from standards_advisor.ids import sha256_text
from standards_advisor.models.common import IntakeConfigRef, LifecyclePhase
from standards_advisor.models.elicitation import IntakeFacet, Question


@dataclass(frozen=True)
class IntakeConfig:
    """One version of the question set."""

    version: str
    questions: list[Question] = field(default_factory=list)
    sha256: str = ""

    def ref(self) -> IntakeConfigRef:
        return IntakeConfigRef(version=self.version, sha256=self.sha256)

    def questions_for(self, phase: LifecyclePhase) -> list[Question]:
        """The questions to put for a run at this phase.

        **Must be deterministic** — see the package docstring. Given the same phase and the same
        file it returns the same list in the same order, because the node calls it once before
        pausing and again on resume, and the answers are matched to it by position and id.
        """
        if phase is not LifecyclePhase.PRE_COLLECTION:
            return []
        return list(self.questions)


def load_intake_config(path: Path) -> IntakeConfig:
    """Load and validate a question set."""
    if not path.is_file():
        raise ConfigError(f"intake question set not found at {path}")

    text = path.read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"intake question set at {path} is not valid TOML: {exc}") from exc

    version = str(raw.get("version") or path.stem)
    if version != path.stem:
        raise ConfigError(
            f"intake question set at {path} declares version {version!r} but its filename "
            f"says {path.stem!r}; the filename is the version"
        )

    entries = raw.get("question")
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"intake question set at {path} has no [[question]] entries")

    questions: list[Question] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        question = _question(entry, path, index)
        if question.id in seen:
            # Answers are matched to questions by id, so a duplicate would silently discard one.
            raise ConfigError(f"intake question set at {path} repeats question id {question.id!r}")
        seen.add(question.id)
        questions.append(question)

    return IntakeConfig(version=version, questions=questions, sha256=sha256_text(text))


def _question(entry: object, path: Path, index: int) -> Question:
    if not isinstance(entry, dict):
        raise ConfigError(f"[[question]] {index} in {path} is not a table")

    missing = {"id", "facet", "text", "why"} - entry.keys()
    if missing:
        raise ConfigError(f"[[question]] {index} in {path} is missing {', '.join(sorted(missing))}")

    facet_value = str(entry["facet"])
    try:
        facet = IntakeFacet(facet_value)
    except ValueError:
        known = ", ".join(sorted(item.value for item in IntakeFacet))
        raise ConfigError(
            f"[[question]] {index} in {path} has facet {facet_value!r}, which nothing maps onto "
            f"a profile field; known facets: {known}"
        ) from None

    return Question(
        id=str(entry["id"]),
        facet=facet,
        text=str(entry["text"]),
        why=str(entry["why"]),
        multiple=bool(entry.get("multiple", True)),
        example=str(entry["example"]) if entry.get("example") is not None else None,
    )
