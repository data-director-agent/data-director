"""Test doubles for code built on the SDK.

`FakeModel` is a `dd_sdk.model.Model` that replies with what a test gives it, so a model-backed
agent's tests need neither a key nor the `anthropic` package (docs/specs/agents.md, Model-backed
personas). Calls made through it go through `dd_sdk.model.call` like any other, so the `chat`
span, the token counts and the `ModelCallLog` are the real ones.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable, Sequence
from typing import Any, Literal

from dd_sdk import security_log
from dd_sdk.model import ModelRequest, ModelResponse, Usage

type Replier = Callable[[ModelRequest], str]

# The tokens a fake call reports using, unless a test says otherwise.
FAKE_USAGE = Usage(100, 40)


class FakeModel:
    """Replies with `replies`: one text for every call, a sequence of texts in turn (the last
    repeated), or a function of the request. Keeps every request in `sent`."""

    def __init__(
        self,
        replies: str | Sequence[str] | Replier = "",
        *,
        refuse: bool = False,
        provider: str = "fake",
        model_id: str = "fake-model",
        answered_by: str | None = None,
        usage: Usage = FAKE_USAGE,
        hosting: Literal["hosted", "local"] = "hosted",
    ) -> None:
        """`answered_by` is the model the response names, if not `model_id`. `hosting` is
        `hosted` unless a test says otherwise, the stricter case for the harness's rules on
        project content."""
        self._replies = replies
        self._refuse = refuse
        self.provider = provider
        self.model_id = model_id
        self.hosting = hosting
        self._answered_by = answered_by
        self._usage = usage
        self.sent: list[ModelRequest] = []

    def send(self, request: ModelRequest) -> ModelResponse:
        self.sent.append(request)
        return ModelResponse(
            text="" if self._refuse else self._reply(request),
            refused=self._refuse,
            model_id=self._answered_by or self.model_id,
            usage=self._usage,
        )

    def _reply(self, request: ModelRequest) -> str:
        if isinstance(self._replies, str):
            return self._replies
        if callable(self._replies):
            return self._replies(request)
        if not self._replies:
            return ""
        return self._replies[min(len(self.sent), len(self._replies)) - 1]


def security_events(records: Iterable[logging.LogRecord]) -> list[dict[str, Any]]:
    """The security events among `records` (pytest's `caplog.records`), as the fields each was
    written with (docs/specs/security.md, Security events)."""
    return [security_log.fields(record) for record in records if record.name == security_log.LOGGER]
