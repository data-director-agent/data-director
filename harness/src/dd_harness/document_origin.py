"""How a document version came about, from the versions it revises (docs/specs/disclosure.md).

A version is one of:

- `model`: drafted by an agent with a language model, and approved as drafted;
- `model_revised`: drafted with a language model, then edited by a person;
- `template`: drafted by an agent by rule, with no generative model, and approved as drafted;
- `template_revised`: drafted by rule, then edited by a person;
- `person`: written by a person.

The disclosure (`dd_harness.disclosure`) and the provenance graph
(`dd_harness.provenance_graph`) both read a version's origin from here, so they cannot disagree.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal

type Origin = Literal["model", "model_revised", "template", "template_revised", "person"]

# The IPTC Digital Source Type vocabulary, as schema.org's `digitalSourceType` takes it.
IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"
DIGITAL_SOURCE_TYPE: dict[Origin, str | None] = {
    "model": IPTC + "trainedAlgorithmicMedia",
    "model_revised": IPTC + "compositeWithTrainedAlgorithmicMedia",
    "template": IPTC + "algorithmicMedia",
    "template_revised": IPTC + "algorithmicMedia",
    "person": None,
}
# How a statement names a document kind (dd_sdk DocumentKind).
KIND_NAMES = {
    "metadata_record": "Metadata record",
    "readme": "README",
    "data_dictionary": "Data dictionary",
    "dmp": "Data management plan",
}


def document_name(kind: str, title: str | None) -> str:
    """A document as a person names it: its kind, and its title if it has one."""
    named = KIND_NAMES.get(kind, kind.replace("_", " "))
    return f"{named}: {title}" if title else named


def version_chain[V: Mapping[str, Any]](
    document_id: str, versions: Sequence[V], version: V
) -> list[V]:
    """The versions from the first `version` revises back to, to `version`, oldest first. Each
    version is a mapping with `version` and, if it revises one, `revises`."""
    by_number = {v["version"]: v for v in versions}
    chain = [version]
    while (revises := chain[0].get("revises")) and revises["version"] in by_number:
        if revises["document_id"] != document_id:
            break
        chain.insert(0, by_number[revises["version"]])
    return chain


def drafted_in(chain: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """The last version of `chain` an agent drafted, or None if a person wrote them all."""
    return next((v for v in reversed(chain) if v.get("drafted_by")), None)


def edited_after_draft(chain: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The versions of `chain` a person wrote after the last draft, oldest first."""
    drafted = drafted_in(chain)
    after = chain[list(chain).index(drafted) + 1 :] if drafted else chain
    return [v for v in after if not v.get("drafted_by")]


def origin(chain: Sequence[Mapping[str, Any]]) -> Origin:
    """How the last version of `chain` came about."""
    drafted = drafted_in(chain)
    if drafted is None:
        return "person"
    edited = bool(edited_after_draft(chain))
    if drafted["drafted_by"]["document_derivation"] == "model":
        return "model_revised" if edited else "model"
    return "template_revised" if edited else "template"
