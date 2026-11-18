"""`spacy.util`, as far as Presidio's modules use it when they are imported."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class _Registry:
    """Every registry, such as `registry.tokenizers`, whose decorators register nothing."""

    def __getattr__(self, name: str) -> Callable[..., Callable[[Any], Any]]:
        return lambda *args, **kwargs: lambda function: function


registry = _Registry()


def is_package(name: str) -> bool:
    """No spaCy model is installed in the browser."""
    return False
