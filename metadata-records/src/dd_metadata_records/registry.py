"""The registered standards and codecs, found by entry point (docs/specs/metadata-standards.md,
invariant 11).

A package registers a codec under the `dd_metadata_records.codecs` group, named by its identifier,
and a standard's definition under `dd_metadata_records.standards`, named by its standard's
identifier, as a `Definition`. A record is read only in a pair of standard and serialisation that
a registered definition covers (invariant 1).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Any, Final

from dd_metadata_records.codecs import Codec, CodecError, Tree
from dd_metadata_records.definition import Definition, DefinitionError
from dd_metadata_records.record import Record

CODECS_GROUP: Final = "dd_metadata_records.codecs"
STANDARDS_GROUP: Final = "dd_metadata_records.standards"


class RecordError(ValueError):
    """The text is not a record in the standard and serialisation it names."""


@dataclass(frozen=True)
class Standard:
    """A registered standard: its definition, with the codec of each serialisation it has."""

    definition: Definition
    codecs: Mapping[str, Codec]

    @property
    def standard_id(self) -> str:
        return self.definition.standard_id

    def read(self, text: str, media_type: str) -> Record:
        """The record `text` holds in the serialisation of `media_type`. Raises `RecordError`."""
        serialisation = self.definition.serialisation(media_type)
        if serialisation is None:
            raise RecordError(f"{self.definition.name} has no serialisation in {media_type}")
        try:
            tree = self.codecs[media_type].parse(text)
        except CodecError as exc:
            raise RecordError(str(exc)) from None
        if not isinstance(tree, dict):
            raise RecordError(f"it is not a {serialisation.name} object")
        for envelope in serialisation.envelopes:
            inner: Any = tree
            for key in envelope:
                inner = inner.get(key) if isinstance(inner, dict) else None
            if isinstance(inner, dict):
                tree = inner
                break
        if serialisation.gap is not None:
            tree = _swapped(tree, serialisation.gap, None)
        return Record(self.definition, media_type, tree)

    def write(self, tree: Tree, media_type: str) -> str:
        """`tree` written in the serialisation of `media_type`, through its codec, each gap (a
        None in the logical tree) as the serialisation writes one (invariant 6)."""
        serialisation = self.definition.serialisation(media_type)
        if serialisation is None or media_type not in self.codecs:
            raise RecordError(f"{self.definition.name} has no serialisation in {media_type}")
        if serialisation.gap is not None:
            tree = _swapped(tree, None, serialisation.gap)
        return self.codecs[media_type].emit(tree)

    def gap(self, media_type: str) -> Any:
        """How a gap is written in the serialisation of `media_type` (invariant 6)."""
        serialisation = self.definition.serialisation(media_type)
        return serialisation.gap if serialisation else None


def _swapped(tree: Any, old: Any, new: Any) -> Any:
    """`tree` with every leaf equal to `old` written as `new`: a serialisation's gap as the
    logical tree's None, or back."""
    if isinstance(tree, dict):
        return {key: _swapped(value, old, new) for key, value in tree.items()}
    if isinstance(tree, list):
        return [_swapped(value, old, new) for value in tree]
    return new if tree == old and type(tree) is type(old) else tree


class Standards:
    """The registered standards, by identifier and by the `conforms_to` URIs they cover."""

    def __init__(self, definitions: Iterable[Definition], codecs: Iterable[Codec]) -> None:
        by_id = {codec.codec_id: codec for codec in codecs}
        self._standards: dict[str, Standard] = {}
        self._by_uri: dict[str, Standard] = {}
        for definition in definitions:
            if definition.standard_id in self._standards:
                raise DefinitionError(f"{definition.standard_id} is registered twice")
            used = {}
            for serialisation in definition.serialisations:
                codec = by_id.get(serialisation.codec_id)
                if codec is None or codec.media_type != serialisation.media_type:
                    raise DefinitionError(
                        f"{definition.standard_id} names codec {serialisation.codec_id} for "
                        f"{serialisation.media_type}, and no such codec is registered"
                    )
                used[serialisation.media_type] = codec
            standard = Standard(definition, used)
            self._standards[definition.standard_id] = standard
            for uri in definition.conforms_to:
                if uri in self._by_uri:
                    raise DefinitionError(f"{uri} is covered by two standards")
                self._by_uri[uri] = standard

    def __iter__(self) -> Any:
        return iter(self._standards.values())

    def get(self, standard_id: str) -> Standard | None:
        return self._standards.get(standard_id)

    def by_uri(self, conforms_to: str | None) -> Standard | None:
        """The standard that covers `conforms_to`, whatever its serialisation."""
        return self._by_uri.get(conforms_to) if conforms_to else None

    def covering(self, conforms_to: str | None, media_type: str | None) -> Standard | None:
        """The standard that covers the pair of `conforms_to` and `media_type`, or None."""
        standard = self.by_uri(conforms_to)
        if standard is None or media_type not in standard.codecs:
            return None
        return standard


def discover() -> Standards:
    """The standards and codecs registered by entry point. Raises `DefinitionError` for one whose
    entry point names something else, or whose name is not its identifier."""
    codecs = []
    for point in entry_points(group=CODECS_GROUP):
        codec = point.load()
        if getattr(codec, "codec_id", None) != point.name:
            raise DefinitionError(f"codec entry point {point.name} is not a codec of that id")
        codecs.append(codec)
    definitions = []
    for point in entry_points(group=STANDARDS_GROUP):
        definition = point.load()
        if not isinstance(definition, Definition) or definition.standard_id != point.name:
            raise DefinitionError(f"standard entry point {point.name} is not its definition")
        definitions.append(definition)
    return Standards(definitions, codecs)
