"""Which agent is calling (docs/specs/model-accounts.md, invariants 7 and 8).

Each agent that calls through the broker holds a broker credential of its own, read once at
start-up like any key (TODO(#808)). It sends the credential where its provider client already sends
an API key (`x-api-key`, or `Authorization: Bearer`), so the agent's adapter changes only its base
URL and its credential.

The broker holds only the SHA-256 digest of each credential, by agent identifier, read once at
start-up from `DD_BROKER_AGENT_CREDENTIALS` (a JSON object, `{"<agent id>": "<hex digest>"}`).
A credential is high-entropy and random, so a plain digest is enough; it is compared in constant
time against every digest held.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping

_HEX_DIGEST = re.compile(r"[0-9a-f]{64}")


def digest(credential: str) -> str:
    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


class AgentCredentials:
    def __init__(self, digests: Mapping[str, str]) -> None:
        self._digests = {agent: bytes.fromhex(value) for agent, value in digests.items()}

    @classmethod
    def from_json(cls, text: str) -> AgentCredentials:
        """Parse the credential list. Raises `ValueError` naming the problem, never a value."""
        try:
            document = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError("the agent credential list is not JSON") from exc
        if not isinstance(document, dict) or not document:
            raise ValueError("the agent credential list is not a non-empty object")
        for agent, value in document.items():
            if not isinstance(value, str) or not _HEX_DIGEST.fullmatch(value):
                raise ValueError(
                    f"the agent credential list's entry for {agent!r} is not a SHA-256 hex digest"
                )
        return cls(document)

    def __len__(self) -> int:
        return len(self._digests)

    def authenticate(self, credential: str | None) -> str | None:
        """The agent whose credential this is, or `None`."""
        if not credential:
            return None
        presented = hashlib.sha256(credential.encode("utf-8")).digest()
        found = None
        for agent, held in self._digests.items():
            # Compare against every entry, so the time taken does not say which one matched.
            if hmac.compare_digest(presented, held):
                found = agent
        return found
