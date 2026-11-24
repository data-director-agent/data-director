"""Which standard's set a chosen repository is checked against, and why (docs/specs/deposit.md,
invariant 5).

In order: the standard the repository's override names; else, when a person chose one, that
standard; else the one standard the repository declares that the deployment has a set for; else,
of several it declares, the first in the deployment's order of preference; else DataCite's, which
any repository that mints DataCite DOIs accepts. Every choice records its reason, and a choice the
researcher should know was assumed carries a warning.

The order of preference is the deployment's: `standard_preference.yaml` beside the sets lists
the standards' sets by `requirement_set_id`, every one once. Without the file, DataCite's set
comes first and the others follow by identifier.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

import yaml

from dd_sdk.contract.models import RequirementSet

PREFERENCE_FILE = "standard_preference.yaml"


class StandardReason(StrEnum):
    """Why a choice resolved to its standard."""

    OVERRIDE = "override"
    CHOSEN = "chosen"
    DECLARED = "declared"
    DECLARED_SEVERAL = "declared_several"
    FALLBACK = "fallback"


class WithSet(Protocol):
    """A loaded standard's set, as `dd_harness.requirements.LoadedSet` holds it."""

    @property
    def requirement_set(self) -> RequirementSet: ...


class StandardChoiceError(ValueError):
    """A preference list, or a person's choice of standard, that cannot be followed."""


@dataclass(frozen=True)
class Choice[S: WithSet]:
    """The standard's set a repository is checked against, why, and what the researcher is
    told was assumed."""

    standard: S
    reason: StandardReason
    warnings: tuple[str, ...] = field(default=())


def load_preference(path: Path) -> list[str] | None:
    """The set identifiers `standard_preference.yaml` lists under `preference`, in order; None if
    there is no file."""
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError as exc:
        raise StandardChoiceError(f"{path}: not YAML: {exc}") from exc
    found = data.get("preference") if isinstance(data, dict) else None
    if not isinstance(found, list) or not all(isinstance(i, str) for i in found):
        raise StandardChoiceError(f"{path}: expected a 'preference' list of requirement set ids")
    return found


def ordered[S: WithSet](
    standards: Sequence[S], preference: Sequence[str] | None, first: str
) -> list[S]:
    """The standards' sets in the deployment's order of preference. Without a preference list,
    the set whose standard is `first` (DataCite's) leads and the others follow by identifier. A
    list must name every set once and nothing else."""
    by_id = {s.requirement_set.requirement_set_id: s for s in standards}
    if preference is None:
        return sorted(
            standards,
            key=lambda s: (
                s.requirement_set.conforms_to != first,
                s.requirement_set.requirement_set_id,
            ),
        )
    unknown = [i for i in preference if i not in by_id]
    missing = [i for i in by_id if i not in preference]
    if unknown or missing or len(set(preference)) != len(preference):
        raise StandardChoiceError(
            f"{PREFERENCE_FILE} must name every standard's set once: unknown {unknown}, "
            f"missing {missing} (docs/specs/deposit.md)"
        )
    return [by_id[i] for i in preference]


def choose[S: WithSet](
    preferred: Sequence[S],
    fallback: S,
    *,
    override: S | None,
    repository_name: str,
    declared: Sequence[str],
    chosen: str | None = None,
) -> Choice[S]:
    """The standard's set a repository is checked against. `preferred` is every standard's set
    in the deployment's order, `fallback` DataCite's, `declared` the standards the registry
    record lists, and `chosen` the `conforms_to` of a standard a person chose, if any. Raises
    `StandardChoiceError` for a choice that names a standard no set is for, or another standard
    than the override's."""
    by_uri = {s.requirement_set.conforms_to: s for s in preferred}
    if chosen is not None and chosen not in by_uri:
        raise StandardChoiceError(f"the deployment has no set for the standard {chosen}")
    if override is not None:
        own = override.requirement_set.conforms_to
        if chosen is not None and chosen != own:
            raise StandardChoiceError(
                f"the deployment's settings for {repository_name} are written for "
                f"{by_uri[own].requirement_set.title}, so its record must be in that standard"
            )
        return Choice(by_uri[own], StandardReason.OVERRIDE)
    if chosen is not None:
        return Choice(by_uri[chosen], StandardReason.CHOSEN)
    matching = [s for s in preferred if set(s.requirement_set.re3data_names) & set(declared)]
    if len(matching) == 1:
        return Choice(matching[0], StandardReason.DECLARED)
    if matching:
        first, others = matching[0], [s.requirement_set.title for s in matching[1:]]
        warning = (
            f"re3data lists several standards the deployment has a set for, for "
            f"{repository_name}: it is checked against {first.requirement_set.title}, the "
            f"deployment's first preference, not {', '.join(others)}"
        )
        return Choice(first, StandardReason.DECLARED_SEVERAL, (warning,))
    listed = ", ".join(declared) if declared else "none"
    warning = (
        f"re3data does not list DataCite for {repository_name} (it lists: {listed}); its "
        "requirements are checked against DataCite's"
    )
    return Choice(fallback, StandardReason.FALLBACK, (warning,))
