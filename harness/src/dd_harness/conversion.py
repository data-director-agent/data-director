"""An approved metadata record converted to another standard (docs/specs/metadata-standards.md,
invariant 9; docs/specs/deposit.md).

A conversion is a package derived from the approved record, never a document and never approved
in the record's place (invariant 2): it is kept by its digest with a `package_built` event of
format `metadata-record`, which names the record it came from by digest (`derived_from`) and as
the document version it is (`documents`), both
standards' definitions, and every value it could not place or placed less precisely. A property
the target's requirement set requires and the source has no value for is never filled in: the
conversion is refused, and says what to add to the approved record.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

from dd_harness.metadata_standards import readable, registered
from dd_harness.projects import PACKAGE_BUILT
from dd_harness.requirements import Requirements
from dd_metadata_records import Standards, convert
from dd_sdk.contract.models import Principal

# The format of a converted record's package (docs/specs/deposit.md, invariant 19).
METADATA_RECORD: Final = "metadata-record"


class Projects(Protocol):
    """What a conversion reads and writes of a project."""

    def metadata_record(self, project_id: str) -> dict[str, Any] | None: ...

    def events(self, project_id: str) -> list[dict[str, Any]]: ...

    def record_package(
        self,
        project_id: str,
        package: bytes,
        *,
        about: Mapping[str, Any],
        acted_for: Principal,
        caused_by: str,
    ) -> str: ...


class ConversionError(ValueError):
    """A conversion asked for that cannot be made: no approved record, or a target that is not a
    registered standard, or is the record's own."""


@dataclass(frozen=True)
class Refused:
    """A conversion refused because the target's requirements need what the record lacks: each
    missing field, by its property in the target and its label, with what to do."""

    missing: tuple[dict[str, str], ...]
    standard: str


@dataclass(frozen=True)
class Converted:
    """A conversion kept as a package: its digest and what its `package_built` event says."""

    digest: str
    about: Mapping[str, Any] = field(default_factory=dict)


def convert_record(
    projects: Projects,
    project_id: str,
    conforms_to: str,
    *,
    requirements: Requirements,
    acted_for: Principal,
    caused_by: str,
    standards: Standards | None = None,
) -> Converted | Refused:
    """Convert the project's approved metadata record to the standard `conforms_to` names, and
    keep it as a package, or refuse it, naming each field the target's set requires that the
    record cannot supply. Raises `ConversionError` for a conversion that cannot be asked for."""
    found = standards or registered()
    approved = projects.metadata_record(project_id)
    record = readable(approved)
    if approved is None or record is None:
        raise ConversionError("the project has no approved metadata record to convert")
    target = found.by_uri(conforms_to)
    if target is None:
        raise ConversionError(f"no registered standard covers {conforms_to}")
    if target.definition is record.definition:
        raise ConversionError(f"the approved record is already in {target.definition.name}")
    conversion = convert(record, target.definition)
    media_type = target.definition.serialisations[0].media_type
    text = target.write(conversion.tree, media_type)
    written = target.read(text, media_type)
    standard_set = requirements.standard_set(conforms_to)
    missing = tuple(
        {
            "property": f.property,
            "label": f.form_label or f.property,
            "question": (
                f"{target.definition.name} requires {f.form_label or f.property}, and the "
                f"approved record gives nothing it can be written from: add it to the record, "
                "and approve it again"
            ),
        }
        for f in (standard_set.fields if standard_set else ())
        if f.obligation.value == "required" and not written.values(f.property, f.qualifier)
    )
    if missing:
        return Refused(missing, target.definition.name)
    source = record.definition
    about = {
        "format": METADATA_RECORD,
        "media_type": media_type,
        "conforms_to": conforms_to,
        "title": target.definition.name,
        # The approved record's version, by its digest and as the document version it is.
        "derived_from": hashlib.sha256(approved["document_text"].encode("utf-8")).hexdigest(),
        "documents": [dict(approved["version_ref"])],
        "standards": {"source": source.describe(), "target": target.definition.describe()},
        "unplaced": list(conversion.unplaced),
        "reduced": [{"path": r.path, "reason": r.reason} for r in conversion.reduced],
    }
    digest = projects.record_package(
        project_id, text.encode("utf-8"), about=about, acted_for=acted_for, caused_by=caused_by
    )
    return Converted(digest, about)


def conversions(projects: Projects, project_id: str) -> list[dict[str, Any]]:
    """The project's converted records, newest first, each as its `package_built` event says."""
    return [
        e
        for e in reversed(projects.events(project_id))
        if e["event"] == PACKAGE_BUILT and e.get("format") == METADATA_RECORD
    ]
