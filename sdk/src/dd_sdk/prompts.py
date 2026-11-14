"""What an agent sent to a language model, and how it reports each call (docs/specs/disclosure.md).

An agent that calls a model records each call with a `ModelCallLog` and returns the log's `calls`
and `prompts` in its `AgentResult`. A call names its prompt by `prompt_digest`. The prompt itself
goes to the harness, which keeps it beside the run under the project's access rules and checks
that it hashes to the digest; it never enters the envelope, the trace or the Process Run Crate.

A prompt is the JSON object of what the agent sent besides sampling parameters: for the Messages
API, `{"system": ..., "messages": [...]}`, and `tools` if any were offered. Its digest is
`dd-prompt-json-v1`: SHA-256 over the JSON with keys sorted, no whitespace, UTF-8. This is not an
evidence canonicalisation (`dd_sdk.evidence`): a prompt is what the agent said, not what it rests
on.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from dd_sdk import model_account
from dd_sdk.contract.models import ModelAccount, ModelCall, now

PROMPT_CANONICALISATION = "dd-prompt-json-v1"

type Prompt = Mapping[str, Any]


def prompt_digest(prompt: Prompt) -> str:
    """The `dd-prompt-json-v1` digest of a prompt."""
    encoded = json.dumps(prompt, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


class ModelCallLog:
    """The model calls of one run, in the order made, and the prompts they name by digest.

    Not shared between runs: an agent makes one per `run`.
    """

    def __init__(self, provider: str) -> None:
        self.provider = provider
        self._calls: list[ModelCall] = []
        self._prompts: dict[str, dict[str, Any]] = {}

    def record(
        self,
        prompt: Prompt,
        model_id: str,
        *,
        called_at: datetime | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        account: ModelAccount | None = None,
    ) -> ModelCall:
        """Record one call. `model_id` is the model the provider's response named, where it
        names one. `account` is whose account paid; by default, what the broker said of the call
        just answered (`dd_sdk.model_account`). Returns the call recorded."""
        digest = prompt_digest(prompt)
        # Taken whether or not `account` is given, so that no later call inherits it.
        reported = model_account.take()
        call = ModelCall(
            model_provider=self.provider,
            model_id=model_id,
            called_at=called_at or now(),
            prompt_digest=digest,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_account=account or reported,
        )
        self._calls.append(call)
        # A round trip through JSON, so what is kept is what the digest covers.
        self._prompts[digest] = json.loads(json.dumps(prompt))
        model_account.collect(call, self._prompts[digest])
        return call

    @property
    def calls(self) -> tuple[ModelCall, ...]:
        return tuple(self._calls)

    @property
    def prompts(self) -> dict[str, dict[str, Any]]:
        return dict(self._prompts)
