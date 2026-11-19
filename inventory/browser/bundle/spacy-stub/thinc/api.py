"""`thinc.api`, as far as Presidio's modules import it."""

from __future__ import annotations

from typing import Any, NoReturn


def get_torch_default_device(*args: Any, **kwargs: Any) -> NoReturn:
    raise ImportError("thinc is not in the browser bundle: no model runs there")
