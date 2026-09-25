"""Who an invocation acts for (Blueprint §5.4, ADR-0018).

An agent must not operate anonymously: every invocation is made on behalf of a named human, and
the envelope and the crate record who. The caller never says so. The authentication boundary
names the principal, the transport hands it to the conductor, and the conductor records it. A
request that carries `acting_for` is refused by the contract, as one naming a profile is.

There is no authentication yet. `OperatorAssertion` is the stub: the deployment's operator names
one principal in configuration, and every invocation is recorded as acting for them with
`assurance: asserted`. On a shared `workbench serve` that means every caller is recorded as the
operator; `asserted` is there so no record claims to have checked who the caller was. Real
authentication replaces `OperatorAssertion` behind `Authenticator` and records `authenticated`
(TODO: its own ADR). Nothing else changes.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from dd_sdk.contract.models import Principal


class IdentityError(Exception):
    """No principal is configured, or the one configured is malformed: a configuration error."""


class Authenticator(Protocol):
    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        """The human a caller acts for, from the headers of its HTTP request (where a credential
        would travel). `None` is a caller with no request: the CLI, the evaluation."""
        ...


@dataclass(frozen=True)
class OperatorAssertion:
    """The stub: the one principal the operator configured, whoever the caller is."""

    principal: Principal

    def principal_for(self, headers: Mapping[str, str] | None) -> Principal:
        return self.principal
