"""What the broker tells its operators (docs/guide/operations/model-broker.md, "What the admin
service reads").

`GET /admin/summary` answers the admin service (`admin/`), which cannot read the broker's store:
that is readable by the broker's user alone. The answer is aggregate. It counts accounts by
provider and sums tokens over everyone by day, payer, provider and model; it names no pseudonym
and carries no account label, key, digest or grant. It also says how the broker is set up: which
agents hold a broker credential, which providers the deployment pays for, whether its calls go
through a base URL such as the LLM gateway, and which origins a person's own account may name.

The route is served only when the deployment sets the operators' credential
(`DD_BROKER_ADMIN_CREDENTIAL`, a digest); otherwise it is not found. A request without the
credential is refused, `operator-unauthenticated`, and recorded as a security event.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from dd_broker.agents import AgentCredentials, OperatorCredential
from dd_broker.enrolment import bearer
from dd_broker.reasons import SERVICE, Reason
from dd_broker.store import Store
from dd_sdk.model_grant import HEADER_REASON
from dd_sdk.security_log import SecurityEvent, emit

log = logging.getLogger("dd_broker")

SUMMARY_PATH = "/admin/summary"
# How far back the token counts go, as the admin service's other figures do.
DAYS = 30


class Broker(Protocol):
    """What the summary reads of `dd_broker.app.Broker`."""

    store: Store
    agents: AgentCredentials
    operator: OperatorCredential | None
    deployment_keys: Mapping[str, str]
    deployment_base_url: str | None
    allowed_base_urls: Collection[str]
    private_base_urls: Collection[str]


def summary(broker: Broker, now: datetime | None = None) -> dict[str, Any]:
    """The aggregate the admin service shows, over the last `DAYS` days."""
    today = (now or datetime.now(UTC)).date()
    since = today - timedelta(days=DAYS - 1)
    found = broker.store.summary(since=since)
    return {
        "since": since.isoformat(),
        "days": DAYS,
        "accounts_by_provider": found.accounts_by_provider,
        "people_with_usage": found.people_with_usage,
        "usage": [
            {
                "day": u.day.isoformat(),
                "payer": u.payer.value,
                "provider": u.provider,
                "model": u.model,
                "input_tokens": u.input_tokens,
                "output_tokens": u.output_tokens,
            }
            for u in found.usage
        ],
        "agents": broker.agents.names(),
        "providers_paid": sorted(broker.deployment_keys),
        "deployment_base_url": broker.deployment_base_url is not None,
        "allowed_base_urls": sorted(broker.allowed_base_urls),
        "private_base_urls": sorted(broker.private_base_urls),
    }


async def answer(broker: Broker, request: Request) -> Response:
    """The summary, for the operators' credential only. A request without it is refused with
    the reason code alone, and recorded as a security event."""
    if broker.operator is None:
        return JSONResponse({"error": "not-found"}, status_code=404)
    if not broker.operator.authenticate(bearer(request)):
        reason = Reason.OPERATOR_UNAUTHENTICATED
        log.info("refused reason=%s status=401", reason.value)
        emit(
            SecurityEvent.BROKER_CALL_REFUSED,
            outcome="failure",
            service=SERVICE,
            reason=reason.value,
        )
        return JSONResponse(
            {"error": reason.value}, status_code=401, headers={HEADER_REASON: reason.value}
        )
    found = await run_in_threadpool(summary, broker)
    return JSONResponse(found, headers={"cache-control": "no-store"})
