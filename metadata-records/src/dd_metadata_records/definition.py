"""A metadata standard's definition: a reviewed file that says how the standard's logical model is
written in each serialisation and what each property means in the pivot
(docs/specs/metadata-standards.md, A standard's definition).

A definition says nothing about what a repository requires: it has no obligation, licence list
or size limit. Adding a standard is adding a definition file and registering it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

import yaml

# The vocabularies a pivot term may come from, by the prefix a CURIE names it with (invariant 7).
TERM_NAMESPACES: Final = {
    "schema": "http://schema.org/",
    "dcterms": "http://purl.org/dc/terms/",
    "dcat": "http://www.w3.org/ns/dcat#",
    "prov": "http://www.w3.org/ns/prov#",
}
# A qualifier value that matches any value of its key.
ANY: Final = "*"
_DRAFTING_KEYS: Final = frozenset({"ask", "publish", "suggest", "filled"})


class DefinitionError(ValueError):
    """A definition file is not a valid definition."""


def expand(term: str) -> str:
    """A term as its full IRI: `dcterms:provenance` as `http://purl.org/dc/terms/provenance`.
    Raises `DefinitionError` for a CURIE of a vocabulary no pivot term may come from."""
    prefix, sep, name = term.partition(":")
    if sep and name.startswith("//"):
        if any(term.startswith(ns) for ns in TERM_NAMESPACES.values()):
            return term
    elif sep and prefix in TERM_NAMESPACES and name:
        return TERM_NAMESPACES[prefix] + name
    raise DefinitionError(f"{term!r} is not a term of {', '.join(TERM_NAMESPACES)}")


@dataclass(frozen=True)
class Qualified:
    """A term for the entries whose qualifier matches `when`."""

    when: Mapping[str, str]
    term: str

    def matches(self, entry: Mapping[str, Any]) -> bool:
        return all(
            key in entry and (wanted == ANY or entry[key] == wanted)
            for key, wanted in self.when.items()
        )

    def matches_qualifier(self, qualifier: Mapping[str, Any]) -> bool:
        return all(
            key in qualifier and (wanted == ANY or qualifier[key] == wanted)
            for key, wanted in self.when.items()
        )


@dataclass(frozen=True)
class Property:
    """One property of a standard, or one part of a structured property's entry."""

    path: str
    value: str | None = None
    term: str | None = None
    qualified: tuple[Qualified, ...] = ()
    parts: Mapping[str, Property] = field(default_factory=dict)

    def term_for(self, entry: Mapping[str, Any] | None = None) -> str | None:
        """The pivot term of an entry of this property: the first qualified term whose qualifier
        the entry matches, else the property's own."""
        for rule in self.qualified:
            if entry is not None and rule.matches(entry):
                return rule.term
        return self.term

    def term_for_qualifier(self, qualifier: Mapping[str, Any] | None) -> str | None:
        """The pivot term a requirement field of this property and `qualifier` is read under."""
        for rule in self.qualified:
            if qualifier and rule.matches_qualifier(qualifier):
                return rule.term
        return self.term

    def terms(self) -> frozenset[str]:
        """Every term an entry of this property may be read under."""
        found = {rule.term for rule in self.qualified}
        return frozenset(found | ({self.term} if self.term else set()))


@dataclass(frozen=True)
class Serialisation:
    """How the standard is written in one media type."""

    media_type: str
    name: str
    codec_id: str
    # The paths a record may be wrapped in, such as an API response's envelope.
    envelopes: tuple[tuple[str, ...], ...] = ()
    gap: Any = None


@dataclass(frozen=True)
class Definition:
    """A standard's definition, as loaded from its file."""

    standard_id: str
    version: int
    title: str
    name: str
    url: str
    conforms_to: tuple[str, ...]
    mapping_source: str
    serialisations: tuple[Serialisation, ...]
    properties: Mapping[str, Property]
    drafting: Mapping[str, Mapping[str, Any]]
    sha256: str

    @property
    def ref(self) -> str:
        """The definition by its identifier and version, as the project log names it."""
        return f"{self.standard_id}@v{self.version}"

    def serialisation(self, media_type: str) -> Serialisation | None:
        return next((s for s in self.serialisations if s.media_type == media_type), None)

    def property(self, path: str) -> Property | None:
        return self.properties.get(path)

    def term(self, path: str, qualifier: Mapping[str, Any] | None = None) -> str | None:
        """The pivot term, as an IRI, a requirement field of `path` and `qualifier` is read
        under, or None if the standard gives the property none."""
        found = self.properties.get(path)
        return found.term_for_qualifier(qualifier) if found else None

    def describe(self) -> dict[str, Any]:
        """The definition by reference and digest, and the codec of each serialisation, as the
        project log records them (invariant 12)."""
        codecs = {s.media_type: s.codec_id for s in self.serialisations}
        return {"ref": self.ref, "sha256": self.sha256, "codecs": codecs}


def load(path: Path) -> Definition:
    """The definition in the YAML file at `path`. Raises `DefinitionError`."""
    raw = path.read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise DefinitionError(f"{path.name} is not a mapping")
    try:
        return _definition(data, hashlib.sha256(raw).hexdigest())
    except (KeyError, TypeError) as exc:
        raise DefinitionError(f"{path.name} is not a valid definition: {exc!r}") from None


def _definition(data: Mapping[str, Any], digest: str) -> Definition:
    properties = {path: _property(path, spec) for path, spec in data["properties"].items()}
    drafting = {str(path): dict(spec) for path, spec in (data.get("drafting") or {}).items()}
    for path, spec in drafting.items():
        if path not in properties:
            raise DefinitionError(f"drafting names {path}, which is not a property")
        if unknown := set(spec) - _DRAFTING_KEYS:
            raise DefinitionError(f"drafting for {path} has unknown keys {sorted(unknown)}")
        if "filled" in spec and set(spec) != {"filled"}:
            raise DefinitionError(f"{path} is filled by rule, so it is never asked or suggested")
    return Definition(
        standard_id=str(data["standard_id"]),
        version=int(data["version"]),
        title=str(data["title"]),
        name=str(data.get("name") or data["title"]),
        url=str(data["url"]),
        conforms_to=tuple(str(uri) for uri in data["conforms_to"]),
        mapping_source=str(data.get("mapping_source") or ""),
        serialisations=tuple(_serialisation(s) for s in data["serialisations"]),
        properties=properties,
        drafting=drafting,
        sha256=digest,
    )


def _serialisation(spec: Mapping[str, Any]) -> Serialisation:
    envelopes: Sequence[Sequence[str]] = spec.get("envelopes") or ()
    return Serialisation(
        media_type=str(spec["media_type"]),
        name=str(spec["name"]),
        codec_id=str(spec["codec"]),
        envelopes=tuple(tuple(str(key) for key in path) for path in envelopes),
        gap=spec.get("gap"),
    )


def _property(path: str, spec: Any) -> Property:
    if isinstance(spec, str):
        return Property(path=path, term=expand(spec))
    if not isinstance(spec, dict):
        raise DefinitionError(f"{path} is neither a term nor a mapping")
    if unknown := set(spec) - {"value", "term", "qualified", "parts"}:
        raise DefinitionError(f"{path} has unknown keys {sorted(unknown)}")
    return Property(
        path=path,
        value=spec.get("value"),
        term=expand(spec["term"]) if spec.get("term") else None,
        qualified=tuple(
            Qualified(when=dict(rule["when"]), term=expand(rule["term"]))
            for rule in spec.get("qualified") or ()
        ),
        parts={key: _property(key, part) for key, part in (spec.get("parts") or {}).items()},
    )
