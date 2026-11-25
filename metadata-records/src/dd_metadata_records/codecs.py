"""Codecs: a serialisation parsed into a generic tree, and a tree written back to it
(docs/specs/metadata-standards.md, invariants 4 and 13).

A codec knows no standard. Its identifier names one byte output for good: the same tree always
writes to the same bytes, so that a digest recorded when a record is approved is the digest of
what is deposited. A codec whose output changes is a new codec, with a new identifier.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final, Protocol

# A record is a few kilobytes; a parser refuses anything far larger before reading it.
MAX_RECORD_BYTES: Final = 1_000_000

# A generic tree: what JSON can hold.
type Tree = dict[str, Any] | list[Any] | str | int | float | bool | None


class CodecError(ValueError):
    """The text is not in the codec's serialisation, or is too large to read."""


class Codec(Protocol):
    """Parses a serialisation into a tree and writes a tree back to it."""

    @property
    def codec_id(self) -> str:
        """The codec's identifier, which names one byte output for good."""
        ...

    @property
    def media_type(self) -> str:
        """The media type of the serialisation."""
        ...

    def parse(self, text: str) -> Tree:
        """The tree `text` holds. Raises `CodecError`."""
        ...

    def emit(self, tree: Tree) -> str:
        """`tree` written in the serialisation, the same text for the same tree."""
        ...


def check_size(text: str) -> None:
    """Refuse text over `MAX_RECORD_BYTES` before it is parsed."""
    if len(text.encode("utf-8")) > MAX_RECORD_BYTES:
        raise CodecError(f"it is over {MAX_RECORD_BYTES} bytes, more than a record holds")


@dataclass(frozen=True)
class JsonCodec:
    """JSON in UTF-8, written with two spaces of indentation, keys in the order the tree gives
    them, characters outside ASCII as they are, and a final newline."""

    codec_id: str = "json-indent-2"
    media_type: str = "application/json"

    def parse(self, text: str) -> Tree:
        check_size(text)
        try:
            tree: Tree = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CodecError(f"it is not JSON ({exc.msg} at line {exc.lineno})") from None
        return tree

    def emit(self, tree: Tree) -> str:
        return json.dumps(tree, ensure_ascii=False, indent=2) + "\n"


JSON: Final = JsonCodec()
