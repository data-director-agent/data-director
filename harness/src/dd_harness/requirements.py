"""Repository requirements: the deployment's requirement sets, and what a choice resolves to.

A researcher may choose any repository in re3data, or, for one re3data does not list, in DataCite
(docs/specs/deposit.md). What a deposit to it must
or should have is not written for each repository. It comes from the deployment's `RequirementSet`s,
kept as YAML under `DD_REPOSITORIES_DIR`:

    standards/<id>.yaml    one per metadata standard, naming it in re3data_names
    overrides/<id>.yaml    what one repository asks beyond its standard, naming it in re3data_id,
                           or in repository_id by its DataCite identifier if re3data lists it not
    suggested.yaml         optional: the identifiers the app offers before a search

A choice resolves to the repository's override, if the deployment has one, and the standard's
set: the one the override names in `conforms_to`, else one the repository's re3data record
declares, else DataCite's, with a warning. The two are merged. A field is identified by its
property, qualifier and term, compared as the term's full IRI; an override may add one, or raise
one from recommended to required, label it and say where its value is supplied, but never lower
one. Documents, and the properties the repository fills in itself, are the union of both, and a
kind either requires is required. Media types, sizes and licences come from the override alone.

A field's term may be left out: it is the one the standard's definition gives the field's
property and qualifier (docs/specs/metadata-standards.md). A field that names a term the definition
gives otherwise is refused, and so is a set whose standard no registered definition covers.

Every set is checked when it is loaded, so a deployment whose sets are malformed, of neither
kind, or contradict one another does not start. Recording the choice in a project is
`ProjectStore.choose_repository`; checking a project against the merged set is
`dd_harness.deposit`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dd_harness.metadata_standards import registered
from dd_metadata_records import Standards
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    RE3DATA_ID_PATTERN,
    REPOSITORY_ID_PATTERN,
    DepositConnector,
    Obligation,
    RequirementField,
    RequirementSet,
)
from dd_sdk.contract.requirements import expand_term, legacy_term

log = logging.getLogger(__name__)

STANDARDS_DIR = "standards"
OVERRIDES_DIR = "overrides"
SUGGESTED_FILE = "suggested.yaml"
# The standard every repository that mints DataCite DOIs accepts, and so the one a repository is
# checked against when it declares no standard the deployment has a set for (docs/specs/deposit.md).
DATACITE = "http://datacite.org/schema/kernel-4"
RE3DATA_ID = re.compile(RE3DATA_ID_PATTERN)
REPOSITORY_ID = re.compile(REPOSITORY_ID_PATTERN)
# The transport and format pairs an override's `deposit` block may name (docs/specs/deposit.md,
# Packagers and transports, invariant 18). The manual transport needs no block.
DEPOSIT_PAIRS = frozenset(
    {
        ("zenodo", "zenodo-deposit"),
        ("figshare", "figshare-item"),
        ("dataverse", "dataverse-dataset"),
        ("sword2", "bagit"),
    }
)


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

    @property
    def repository_id(self) -> str | None:
        """An override's repository, by its re3data identifier or its DataCite one."""
        return self.requirement_set.re3data_id or self.requirement_set.repository_id


@dataclass(frozen=True)
class Resolved:
    """What one choice of repository resolved to."""

    repository_id: str
    repository_name: str
    declared_standards: tuple[str, ...]
    standard: LoadedSet
    override: LoadedSet | None
    warnings: tuple[str, ...]

    @property
    def re3data_id(self) -> str | None:
        return self.repository_id if RE3DATA_ID.fullmatch(self.repository_id) else None

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
            "repository_id": self.repository_id,
            **({"re3data_id": self.re3data_id} if self.re3data_id else {}),
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
                        update={
                            "obligation": field.obligation,
                            "form_label": field.form_label,
                            "supplied_on": field.supplied_on or ours.supplied_on,
                        }
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
        merged["filled_by_repository"] = list(
            dict.fromkeys(p for s in self.sets for p in s.requirement_set.filled_by_repository)
        )
        merged["warnings"] = list(self.warnings)
        merged["unconfirmed"] = list(
            dict.fromkeys(item for s in self.sets for item in s.requirement_set.unconfirmed)
        )
        merged["guidance"] = list(
            dict.fromkeys(page for s in self.sets for page in s.requirement_set.guidance)
        )
        # A standard's url describes the standard, not where to deposit.
        if override is not None and override.requirement_set.url is not None:
            merged["repository_url"] = override.requirement_set.url
        return merged


class Requirements:
    """The deployment's requirement sets, checked against one another."""

    def __init__(
        self,
        standards: Iterable[LoadedSet],
        overrides: Iterable[LoadedSet],
        suggested: Sequence[str] = (),
        definitions: Standards | None = None,
    ) -> None:
        for repository_id in suggested:
            if not REPOSITORY_ID.fullmatch(repository_id):
                raise RequirementsError(
                    f"suggested repository {repository_id!r} is neither a re3data identifier "
                    "(r3d + 9 digits) nor a DataCite one"
                )
        self._suggested = tuple(suggested)
        self.standards = sorted(standards, key=lambda s: s.requirement_set.requirement_set_id)
        self.overrides = sorted(overrides, key=lambda s: s.requirement_set.requirement_set_id)
        _unique("requirement_set_id", (s.requirement_set.requirement_set_id for s in self.all))
        _unique("conforms_to", (s.requirement_set.conforms_to for s in self.standards))
        _unique(
            "re3data_names", (n for s in self.standards for n in s.requirement_set.re3data_names)
        )
        _unique("repository", (s.repository_id for s in self.overrides))
        self._by_standard = {s.requirement_set.conforms_to: s for s in self.standards}
        self._by_repository = {s.repository_id: s for s in self.overrides}
        for standard in self.standards:
            _distinct_terms(
                standard.requirement_set.requirement_set_id, standard.requirement_set.fields
            )
        if DATACITE not in self._by_standard:
            raise RequirementsError(
                f"no standard's set conforms to {DATACITE}: DataCite's is the one a repository "
                "is checked against when it declares no other (docs/specs/deposit.md)"
            )
        for override in self.overrides:
            self._check_override(override)
        for loaded in self.all:
            _check_definition(loaded.requirement_set, definitions or registered())

    @property
    def suggested(self) -> tuple[str, ...]:
        """The repositories to offer a researcher before they search, by identifier: those the
        deployment has an override for, then those `suggested.yaml` lists, each once."""
        overridden = (s.repository_id for s in self.overrides)
        return tuple(dict.fromkeys([*(i for i in overridden if i), *self._suggested]))

    @property
    def all(self) -> list[LoadedSet]:
        return [*self.standards, *self.overrides]

    def connector(self, repository_id: str) -> DepositConnector | None:
        """How the harness may deposit a draft to the repository through its API, as its override
        says now; None when it is deposited to by hand. Read when a deposit is approved, not when
        the repository is chosen, so the approval names the connector as configured at that
        moment (docs/specs/deposit.md)."""
        override = self._by_repository.get(repository_id)
        return None if override is None else override.requirement_set.deposit

    def resolve(
        self, repository_id: str, repository_name: str, declared_standards: Sequence[str] = ()
    ) -> Resolved:
        """What a repository's requirements are, from its identifier and the metadata standards
        its registry record declares. Raises `RequirementsError` for a malformed identifier."""
        if not REPOSITORY_ID.fullmatch(repository_id):
            raise RequirementsError(
                f"{repository_id!r} is neither a re3data identifier (r3d + 9 digits) nor a "
                "DataCite one"
            )
        if not repository_name.strip():
            raise RequirementsError("a chosen repository needs its name")
        declared = tuple(dict.fromkeys(declared_standards))
        warnings: list[str] = []
        override = self._by_repository.get(repository_id)
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
        return Resolved(
            repository_id, repository_name, declared, standard, override, tuple(warnings)
        )

    def _check_override(self, override: LoadedSet) -> None:
        own = override.requirement_set
        standard = self._by_standard.get(own.conforms_to)
        if standard is None:
            raise RequirementsError(
                f"override {own.requirement_set_id!r} builds on {own.conforms_to}, "
                "for which there is no standard's set"
            )
        theirs = {_field_key(f): f for f in standard.requirement_set.fields}
        _distinct_terms(own.requirement_set_id, [*theirs.values(), *own.fields])
        for field in own.fields:
            base = theirs.get(_field_key(field))
            if (
                base is not None
                and base.obligation is Obligation.REQUIRED
                and field.obligation is Obligation.RECOMMENDED
            ):
                raise RequirementsError(
                    f"override {own.requirement_set_id!r} lowers {field.property} from required "
                    f"to recommended; an override may add or raise, never lower "
                    f"(docs/specs/deposit.md)"
                )


def load_requirements(directory: Path, definitions: Standards | None = None) -> Requirements:
    """Load the sets under `directory`, reading each field's term from its standard's definition
    in `definitions`, the registered ones by default. The path is the operator's, never a
    caller's."""
    if not directory.is_dir():
        raise RequirementsError(f"repository requirements not found at {directory}")
    schema = ClassSchema.of(RequirementSet)
    found = definitions or registered()
    standards = [_load(p, schema, found, override=False) for p in _files(directory / STANDARDS_DIR)]
    overrides = [_load(p, schema, found, override=True) for p in _files(directory / OVERRIDES_DIR)]
    return Requirements(standards, overrides, _suggested(directory / SUGGESTED_FILE), found)


def _suggested(path: Path) -> list[str]:
    """The identifiers `suggested.yaml` lists under `re3data_ids`; none if there is no file."""
    if not path.is_file():
        return []
    try:
        data = yaml.safe_load(path.read_bytes())
    except yaml.YAMLError as exc:
        raise RequirementsError(f"{path}: not YAML: {exc}") from exc
    ids = data.get("re3data_ids") if isinstance(data, dict) else None
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise RequirementsError(f"{path}: expected a 're3data_ids' list of re3data identifiers")
    return ids


def _files(directory: Path) -> list[Path]:
    return sorted(directory.glob("*.yaml")) if directory.is_dir() else []


def _load(path: Path, schema: ClassSchema, definitions: Standards, *, override: bool) -> LoadedSet:
    raw = path.read_bytes()
    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        raise RequirementsError(f"{path}: not YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise RequirementsError(f"{path}: not a mapping")
    data = _defined_terms(_legacy_terms(path, data), definitions)
    errors = schema.errors(data)
    if errors:
        raise RequirementsError(f"{path}: not a RequirementSet: {'; '.join(errors)}")
    found = RequirementSet.model_validate(data)
    misplaced = _misplaced(found) if override else _override_only(found)
    if misplaced:
        kind = "an override" if override else "a standard's set"
        raise RequirementsError(
            f"{path}: {kind} may not give {', '.join(misplaced)} (docs/specs/deposit.md)"
        )
    connector = found.deposit
    if connector is not None and (connector.transport, connector.format) not in DEPOSIT_PAIRS:
        raise RequirementsError(
            f"{path}: deposit names transport {connector.transport!r} with format "
            f"{connector.format!r}, which is not a pair docs/specs/deposit.md allows"
        )
    if override and (found.re3data_id is None) == (found.repository_id is None):
        raise RequirementsError(
            f"{path}: an override names its repository once, in re3data_id or, for one re3data "
            "does not list, in repository_id"
        )
    if not override and not found.re3data_names:
        raise RequirementsError(f"{path}: a standard's set names its standard in re3data_names")
    return LoadedSet(found, hashlib.sha256(raw).hexdigest())


def _override_only(found: RequirementSet) -> list[str]:
    """What a standard's set gives that only an override may."""
    given = [
        key
        for key in (
            "re3data_id",
            "repository_id",
            "max_file_size",
            "max_item_size",
            "licences",
            "deposit",
        )
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
    return field.property, json.dumps(field.qualifier, sort_keys=True), expand_term(field.term)


def _legacy_terms(path: Path, data: dict[str, Any]) -> dict[str, Any]:
    """A set whose fields name a schema.org local name in `schema_org`, as sets did before terms
    were IRIs, read with `schema:` terms (#1357), and a warning to rewrite it."""
    fields = data.get("fields")
    if not isinstance(fields, list) or not any(
        isinstance(f, dict) and "schema_org" in f for f in fields
    ):
        return data
    log.warning(
        "%s: a field names schema_org, read as a schema: term; write it as term instead "
        "(docs/specs/deposit.md)",
        path,
    )
    return {**data, "fields": [legacy_term(f) for f in fields]}


def _defined_terms(data: dict[str, Any], definitions: Standards) -> dict[str, Any]:
    """A set whose fields leave out their term, with the term its standard's definition gives
    each field's property and qualifier. A field the definition gives no term keeps none, and the
    schema refuses it."""
    fields = data.get("fields")
    standard = definitions.by_uri(data.get("conforms_to"))
    if standard is None or not isinstance(fields, list):
        return data
    filled = []
    for field in fields:
        if (
            isinstance(field, dict)
            and "term" not in field
            and isinstance(field.get("property"), str)
        ):
            term = standard.definition.term(field["property"], field.get("qualifier"))
            field = {**field, "term": term} if term else field
        filled.append(field)
    return {**data, "fields": filled}


def _check_definition(found: RequirementSet, definitions: Standards) -> None:
    """Refuse a set whose standard no registered definition covers (invariant 11 of
    docs/specs/metadata-standards.md), or a field that names a term other than the one the
    standard's definition gives its property and qualifier."""
    standard = definitions.by_uri(found.conforms_to)
    if standard is None:
        raise RequirementsError(
            f"{found.requirement_set_id!r} follows {found.conforms_to}, which no registered "
            "standard's definition covers (docs/specs/metadata-standards.md)"
        )
    definition = standard.definition
    for field in found.fields:
        given = definition.term(field.property, field.qualifier)
        if given is not None and given != expand_term(field.term):
            raise RequirementsError(
                f"{found.requirement_set_id!r} reads {_described(_named(field))} under "
                f"{field.term}, but {definition.ref} gives it {given}; a field's term is its "
                "standard's (docs/specs/metadata-standards.md)"
            )


def _named(field: RequirementField) -> tuple[str, str]:
    return field.property, json.dumps(field.qualifier, sort_keys=True)


def _distinct_terms(set_id: str, fields: Iterable[RequirementField]) -> None:
    """Refuse two fields, of a set or of an override merged on its standard, that share a term,
    compared as its full IRI. A record's values are checked under their field's term, so the
    value of one would satisfy the other: a lineage mapped to `description` would pass on the
    abstract alone."""
    seen: dict[str, tuple[str, str]] = {}
    for field in fields:
        named = field.property, json.dumps(field.qualifier, sort_keys=True)
        other = seen.setdefault(expand_term(field.term), named)
        if other != named:
            raise RequirementsError(
                f"{set_id!r} maps both {_described(other)} and {_described(named)} to "
                f"{field.term}, so a value of one would be taken for the other; "
                "give each field its own term (docs/specs/deposit.md)"
            )


def _described(named: tuple[str, str]) -> str:
    prop, qualifier = named
    return prop if qualifier == "null" else f"{prop} {qualifier}"


def _unique(what: str, values: Iterable[Any]) -> None:
    seen: set[Any] = set()
    for value in values:
        if value in seen:
            raise RequirementsError(f"two requirement sets give {what} {value!r}")
        seen.add(value)
