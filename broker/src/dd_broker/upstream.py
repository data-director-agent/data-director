"""What the broker makes of a provider's answer that is not a usable `200`, and the log line that
says why (docs/specs/model-accounts.md).

Each failure is logged with the provider's own HTTP status, or the kind of connection error, so an
operator can tell a refused key from a wrong address or an outage. The provider's text and the
address called are never logged: the text might echo a key.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from dd_broker.reasons import Reason, Refused
from dd_sdk.model_grant import Payer

log = logging.getLogger("dd_broker")


def unreachable(exc: httpx.HTTPError, payer: Payer, provider: str) -> Refused:
    """The refusal for a provider that could not be reached."""
    # The exception's type, not its text, which names the address called.
    log.warning(
        "provider unreachable error=%s payer=%s provider=%s",
        type(exc).__name__,
        payer.value,
        provider,
    )
    return Refused(502, Reason.PROVIDER_UNREACHABLE)


def answered(answer: httpx.Response, payer: Payer, provider: str, model: str) -> dict[str, Any]:
    """The provider's answer as a JSON object, or the refusal that its failure calls for."""
    if answer.status_code != 200:
        raise failure(answer.status_code, payer, provider, model)
    try:
        document = answer.json()
    except ValueError:
        document = None
    if not isinstance(document, dict):
        log.warning(
            "provider answered 200 without a JSON object payer=%s provider=%s content-type=%s",
            payer.value,
            provider,
            answer.headers.get("content-type"),
        )
        raise Refused(502, Reason.PROVIDER_ERROR)
    return document


def failure(status: int, payer: Payer, provider: str, model: str) -> Refused:
    """The refusal for a provider's non-`200` answer."""
    if status in (401, 403) and payer is Payer.DEPLOYMENT:
        log.error("the provider refused the deployment's key (HTTP %d)", status)
    else:
        log.warning(
            "provider failed status=%d payer=%s provider=%s model=%s",
            status,
            payer.value,
            provider,
            model,
        )
    if status in (401, 403):
        if payer is Payer.OWN:
            return Refused(403, Reason.MODEL_ACCOUNT_REJECTED)
        return Refused(502, Reason.PROVIDER_ERROR)
    if status == 429:
        return Refused(
            429, Reason.MODEL_ACCOUNT_LIMIT if payer is Payer.OWN else Reason.PROVIDER_ERROR
        )
    if status == 400:
        return Refused(400, Reason.REQUEST_INVALID)
    if status == 529:
        return Refused(529, Reason.PROVIDER_ERROR)
    return Refused(502, Reason.PROVIDER_ERROR)
