"""`spacy.language.Language`, as far as Presidio's modules use it when they are imported."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class Language:
    @classmethod
    def factory(cls, *args: Any, **kwargs: Any) -> Callable[[Any], Any]:
        """Registers nothing: the decorated function is returned unchanged."""
        return lambda function: function
