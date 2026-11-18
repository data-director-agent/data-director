"""`spacy.tokens`: the classes Presidio names, and an empty `Doc` for its `NoOpNlpEngine`."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any


class _Extensible:
    @classmethod
    def set_extension(cls, *args: Any, **kwargs: Any) -> None:
        return None

    @classmethod
    def has_extension(cls, *args: Any, **kwargs: Any) -> bool:
        return False


class Doc(_Extensible):
    """An empty document: the `NoOpNlpEngine` makes one per text, with no words."""

    def __init__(self, vocab: Any = None, words: Sequence[str] = (), **kwargs: Any) -> None:
        if words:
            raise ImportError("spaCy is not in the browser bundle: a Doc here holds no words")
        self.vocab = vocab
        self.ents: tuple[Any, ...] = ()

    def __iter__(self) -> Iterator[Any]:
        return iter(())

    def __len__(self) -> int:
        return 0


class Span(_Extensible):
    pass


class SpanGroup(_Extensible):
    pass


class Token(_Extensible):
    pass
