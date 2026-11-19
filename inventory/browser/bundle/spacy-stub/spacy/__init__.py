"""A stand-in for spaCy in the browser bundle of dd-inventory (inventory/browser/README.md).

Presidio imports spaCy at module level, even when it runs, as here, with its `NoOpNlpEngine` and
no language model. spaCy does not build for Pyodide, so the bundle installs this instead: the
names Presidio's modules import, and nothing that processes language. What would need spaCy
itself raises `ImportError`. Raised upstream with Presidio so that the import becomes optional
(docs/specs/personal-data.md); `inventory/tests/test_spacy_stub.py` checks it still suffices.
"""

from __future__ import annotations

from typing import Any, NoReturn

from spacy import language, pipeline, tokens, util, vocab
from spacy.language import Language

__all__ = ["Language", "blank", "language", "load", "pipeline", "require_gpu", "tokens", "util"]
__all__ += ["vocab"]
__version__ = "0.0.0+stub"


def _absent(*args: Any, **kwargs: Any) -> NoReturn:
    raise ImportError("spaCy is not in the browser bundle: only pattern recognisers run there")


blank = load = _absent


def require_gpu(*args: Any, **kwargs: Any) -> bool:
    return False
