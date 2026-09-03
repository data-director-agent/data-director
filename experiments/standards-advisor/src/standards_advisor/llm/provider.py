"""The whole provider seam (§1.4).

"Any chat model with a broadly standard API, reached through one narrow interface. Which model
was used is recorded with every run, and switching model or provider must not mean changing the
pipeline. Nothing in the design may depend on a particular vendor's behaviour."

So this module is deliberately small. `init_chat_model` takes a `"provider:model"` string, and
`langchain-anthropic` is the only provider package installed — adding another is an install plus
a change to `DD_MODEL_ID`, with no pipeline code touched.

**No sampling parameters are sent by default.** `temperature`, `top_p` and `top_k` are removed
on the current Anthropic models and are rejected with an HTTP 400, so a `temperature=0` default
would fail outright. Reproducibility comes from recording the model id, the parameters actually
sent, and the prompt version and hash — not from a sampling parameter. Tests get determinism
from a fake model instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from langchain.chat_models import init_chat_model

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

DEFAULT_MODEL_ID = "anthropic:claude-opus-5"

# Retries and timeout are transport concerns, not model behaviour, so they are set here rather
# than left to each caller.
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT_SECONDS = 60


def get_model(model_id: str, params: dict[str, Any] | None = None) -> BaseChatModel:
    """Build a chat model from a `"provider:model"` string.

    `params` is passed through verbatim and is empty by default. Whatever is passed must be
    recorded by the caller in the run record — the *parameters actually sent*, never the ones
    intended.
    """
    model = init_chat_model(
        model_id,
        max_retries=DEFAULT_MAX_RETRIES,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        **(params or {}),
    )
    # `init_chat_model` is annotated loosely; the seam promises a BaseChatModel.
    return cast("BaseChatModel", model)
