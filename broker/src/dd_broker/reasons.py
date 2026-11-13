"""Why the broker refused a call, or why a call failed, as a short code
(docs/specs/model-accounts.md).

The broker answers every refusal with one of these codes in the `X-DD-Reason` header and in the
error body, and never with a provider's own error text, which might echo a key. The three
`model-account-*` codes are the run outcomes of invariant 10: the agent's SDK turns each into
the `ReasonCode` of the same name in snake case, and the run ends `abstained`
(`dd_sdk.model_account`).
"""

from __future__ import annotations

from enum import StrEnum


class Reason(StrEnum):
    # The calling agent.
    AGENT_UNAUTHENTICATED = "agent-unauthenticated"
    # The grant.
    GRANT_MISSING = "grant-missing"
    GRANT_INVALID = "grant-invalid"
    GRANT_EXPIRED = "grant-expired"
    GRANT_AGENT_MISMATCH = "grant-agent-mismatch"
    MODEL_NOT_GRANTED = "model-not-granted"
    # The enrolment ticket.
    TICKET_MISSING = "ticket-missing"
    TICKET_INVALID = "ticket-invalid"
    TICKET_EXPIRED = "ticket-expired"
    TICKET_USED = "ticket-used"
    # The request.
    REQUEST_INVALID = "request-invalid"
    STREAMING_UNSUPPORTED = "streaming-unsupported"
    # Whose account pays.
    MODEL_ACCOUNT_MISSING = "model-account-missing"
    MODEL_ACCOUNT_REJECTED = "model-account-rejected"
    MODEL_ACCOUNT_LIMIT = "model-account-limit"
    ACCOUNT_UNSUPPORTED = "account-unsupported"
    DEPLOYMENT_ACCOUNT_UNAVAILABLE = "deployment-account-unavailable"
    BASE_URL_REFUSED = "base-url-refused"
    # The provider.
    PROVIDER_ERROR = "provider-error"
    PROVIDER_UNREACHABLE = "provider-unreachable"
    # The broker itself, such as a sealed key that does not open.
    BROKER_ERROR = "broker-error"


class Refused(Exception):
    """A call the broker will not make, or that failed, with the HTTP status to answer and the
    reason code. The message is the code: it never carries a key, a grant or a provider's text."""

    def __init__(self, status: int, reason: Reason) -> None:
        super().__init__(reason.value)
        self.status = status
        self.reason = reason
