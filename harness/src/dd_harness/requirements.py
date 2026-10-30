"""Repository requirements: the deployment's requirement sets, and what a choice resolves to.

A researcher may choose any repository in re3data (ADR-0038). What a deposit to it must or should
have is not written for each repository. It comes from the deployment's `RequirementSet`s, kept
as YAML under `DD_REPOSITORIES_DIR`:

    standards/<id>.yaml    one per metadata standard, naming it in re3data_names
    overrides/<id>.yaml    what one repository asks beyond its standard, naming it in re3data_id

A choice resolves to the repository's override, if the deployment has one, and the standard's
set: the one the override names in `conforms_to`, else one the repository's re3data record
declares, else DataCite's, with a warning. The two are merged. A field is identified by its
property, qualifier and schema.org term; an override may add one, or raise one from recommended
to required and label it, but never lower one. Documents are the union of both, and a kind
either requires is required. Media types, sizes and licences come from the override alone.

Every set is checked when it is loaded, so a deployment whose sets are malformed, of neither
kind, or contradict one another does not start. Recording the choice in a project is
`ProjectStore.choose_repository`; checking a project against the merged set is TODO(#19, #202).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import Obligation, RequirementField, RequirementSet

STANDARDS_DIR = "standards"
OVERRIDES_DIR = "overrides"
# The standard every repository that mints DataCite DOIs accepts, and so the one a repository is
# checked against when it declares no standard the deployment has a set for (ADR-0038).
DATACITE = "http://datacite.org/schema/kernel-4"
RE3DATA_ID = re.compile(r"^r3d[0-9]{9}$")


class RequirementsError(ValueError):
    """A requirement set is malformed or contradicts another, or a choice cannot be resolved."""


@dataclass(frozen=True)
class LoadedSet:
    requirement_set: RequirementSet
    # The SHA-256 of the file's bytes, as a run records its profile's `policy_digest`.
    sha256: str

    @property
    def ref(self) -> str:
        return f"{self.requirement_set.requirement_set_id}@v{self.requirement_set.version}"

    def describe(self) -> dict[str, str]:
        return {"ref": self.ref, "sha256": self.sha256}


@dataclass(frozen=True)
class Resolved:
    """What one choice of repository resolved to."""

    re3data_id: str
    repository_name: str
    declared_standards: tuple[str, ...]
    standard: LoadedSet
    override: LoadedSet | None
    warnings: tuple[str, ...]

    @property
    def sets(self) -> tuple[LoadedSet, ...]:
        return (self.standard,) if self.override is None else (self.standard, self.override)

    def requirements(self) -> dict[str, Any]:
        """The merged set, as the document a drafter is given and validation reads."""
        standard, override = self.standard.requirement_set, self.override
        fields = {_field_key(f): f for f in standard.fields}
        required = list(standard.required_documents)
        recommended = list(standard.recommended_documents)
        merged: dict[str, Any] = {
            "re3data_id": self.re3data_id,
            "repository_name": self.repository_name,
            "conforms_to": standard.conforms_to,
            "requirement_sets": [s.describe() for s in self.sets],
        }
        if override is not None:
            for field in override.requirement_set.fields:
                key = _field_key(field)
                ours = fields.get(key)
                # Lowering an obligation is refused when the sets are loaded.
                fields[key] = (
                    field
                    if ours is None
                    else ours.model_copy(
                        update={"obligation": field.obligation, "form_label": field.form_label}
                    )
                )
            required += override.requirement_set.required_documents
            recommended += override.requirement_set.recommended_documents
            own = override.requirement_set
            merged["media_types"] = list(own.media_types)
            for limit in ("max_file_size", "max_item_size", "licences"):
                if getattr(own, limit) is not None:
                    merged[limit] = getattr(own, limit)
        required = list(dict.fromkeys(required))
        merged["fields"] = [f.model_dump(mode="json", exclude_none=True) for f in fields.values()]
        merged["required_documents"] = [str(k) for k in required]
        merged["recommended_documents"] = [
            str(k) for k in dict.fromkeys(recommended) if k not in required
        ]
        merged["warnings"] = list(self.warnings)
        return merged


class Requirements:
    """The deployment's requirement sets, checked against one another."""

    def __init__(self, standards: Iterable[LoadedSet], overrides: Iterable[LoadedSet]) -> None:
        self.standards = sorted(standards, key=lambda s: s.requirement_set.requirement_set_id)
        self.overrides = sorted(overrides, key=lambda s: s.requirement_set.requirement_set_id)
        _unique("requirement_set_id", (s.requirement_set.requirement_set_id for s in self.all))
        _unique("conforms_to", (s.requirement_set.conforms_to for s in self.standards))
        _unique(
            "re3data_names", (n for s in self.standards for n in s.requirement_set.re3data_names)
        )
        _unique("re3data_id", (s.requirement_set.re3data_id for s in self.overrides))
        self._by_standard = {s.requirement_set.conforms_to: s for s in self.standards}
        self._by_repository = {s.requirement_set.re3data_id: s for s in self.overrides}
        if DATACITE not in self._by_standard:
            raise RequirementsError(
                f"no standard's set conforms to {DATACITE}: DataCite's is the one a repository "
                "is checked against when it declares no other (ADR-0038)"
            )
        for override in self.overrides:
            self._check_override(override)

    @property
    def all(self) -> list[LoadedSet]:
        return [*self.standards, *self.overrides]

    def resolve(
        self, re3data_id: str, repository_name: str, declared_standards: Sequence[str] = ()
    ) -> Resolved:
        """What a repository's requirements are, from its re3data identifier and the metadata
        standards its re3data record declares. Raises `RequirementsError` for a malformed one."""
        if not RE3DATA_ID.fullmatch(re3data_id):
            raise RequirementsError(f"{re3data_id!r} is not a re3data identifier (r3d + 9 digits)")
        if not repository_name.strip():
            raise RequirementsError("a chosen repository needs its name")
        declared = tuple(dict.fromkeys(declared_standards))
        warnings: list[str] = []
        override = self._by_repository.get(re3data_id)
        if override is not None:
            standard = self._by_standard[override.requirement_set.conforms_to]
        else:
            matching = [
                s for s in self.standards if set(s.requirement_set.re3data_names) & set(declared)
            ]
            if matching:
                standard = matching[0]
            else:
                standard = self._by_standard[DATACITE]
                listed = ", ".join(declared) if declared else "none"
                warnings.append(
                    f"re3data does not list DataCite for {repository_name} (it lists: {listed}); "
                    "its requirements are checked against DataCite's"
                )
            warnings.append(
                f"the deployment has no override for {repository_name}: only "
                f"{standard.requirement_set.title} is checked, not the repository's own form, "
                "formats, sizes or licences"
            )
        return Resolved(re3data_id, repository_name, declared, standard, override, tuple(warnings))

    def _check_override(self, override: LoadedSet) -> None:
        own = override.requirement_set
        standard = self._by_standard.get(own.conforms_to)
        if standard is None:
            raise RequirementsError(
                f"override {own.requirement_set_id!r} builds on {own.conforms_to}, "
                "for which there is no standard's set"
            )
        theirs = {_field_key(f): f for f in standard.requirement_set.fields}
        for field in own.fields:
            base = theirs.get(_field_key(field))
            if (
                base is not None
                and base.obligation is Obligation.REQUIRED
                and field.obligation is Obligation.RECOMMENDED
            ):
                raise RequirementsError(
                    f"override {own.requirement_set_id!r} lowers {field.property} from required "
                    f"to recommended; an override may add or raise, never lower (ADR-0038)"
                )


def load_requirements(directory: Path) -> Requirements:
    """Load the sets under `directory`. The path is the operator's, never a caller's."""
    if not directory.is_dir():
        raise RequirementsError(f"repository requirements not found at {directory}")
    schema = ClassSchema.of(RequirementSet)
    standards = [_load(p, schema, override=False) for p in _files(directory / STANDARDS_DIR)]
    overrides = [_load(p, schema, override=True) for p in _files(directory / OVERRIDES_DIR)]
    return Requirements(standards, overrides)


def _files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.yaml")) if directory.is_dir() else []


def _load(path: Path, schema: ClassSchema, *, override: bool) -> LoadedSet:
    raw = path.read_bytes()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RequirementsError(f"{path}: not YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RequirementsError(f"{path}: not a mapping")
    errors = schema.errors(data)
    if errors:
        raise RequirementsError(f"{path}: not a RequirementSet: {'; '.join(errors)}")
    found = RequirementSet.model_validate(data)
    misplaced = _misplaced(found) if override else _override_only(found)
    if misplaced:
        kind = "an override" if override else "a standard's set"
        raise RequirementsError(f"{path}: {kind} may not give {', '.join(misplaced)} (ADR-0038)")
    if override and found.re3data_id is None:
        raise RequirementsError(f"{path}: an override names its repository in re3data_id")
    if not override and not found.re3data_names:
        raise RequirementsError(f"{path}: a standard's set names its standard in re3data_names")
    return LoadedSet(found, hashlib.sha256(raw).hexdigest())


def _override_only(found: RequirementSet) -> list[str]:
    """What a standard's set gives that only an override may."""
    given = [
        key
        for key in ("re3data_id", "max_file_size", "max_item_size", "licences")
        if getattr(found, key) is not None
    ]
    if found.media_types:
        given.append("media_types")
    if any(f.form_label is not None for f in found.fields):
        given.append("form_label")
    return given


def _misplaced(found: RequirementSet) -> list[str]:
    """What an override gives that only a standard's set may."""
    return ["re3data_names"] if found.re3data_names else []


def _field_key(field: RequirementField) -> tuple[str, str, str]:
    return field.property, json.dumps(field.qualifier, sort_keys=True), field.schema_org


def _unique(what: str, values: Iterable[Any]) -> None:
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            raise RequirementsError(f"two requirement sets give {what} {value!r}")
        seen.add(value)
