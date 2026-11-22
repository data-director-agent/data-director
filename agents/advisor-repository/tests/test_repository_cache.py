"""The FAIRsharing record re3data cross-references, read through the live route's local cache
(#327): a repeated run asks nothing and cites the cache; an outage cites the expired copy, stale."""

from __future__ import annotations

from pathlib import Path

import httpx
from test_repository_agent import agent, invoke, re3data  # noqa: F401 (re3data is a fixture)
from test_repository_sources import FAIRSHARING_JSON

from dd_agent_advisor_repository.classes import RepositoryNeeds, RepositoryRef
from dd_agent_advisor_repository.live import FairsharingLive
from dd_agent_advisor_repository.snapshot import FairsharingSnapshot, Re3dataRegistry
from dd_sdk.contract.models import Envelope, EvidenceItem, OutcomeStatus
from dd_sdk.registry.caching import memory_cache
from dd_sdk.registry.fairsharing import FairsharingClient

DATABASE = "FAIRsharing.1ky0cs"


def _cited(env: Envelope) -> EvidenceItem:
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    return next(e for e in env.evidence if e.source_id == DATABASE)


def test_a_repeated_run_cites_the_cache_and_an_outage_the_expired_copy(
    runs_dir: Path,
    re3data: Re3dataRegistry,  # noqa: F811
) -> None:
    clock, down, asked = [1_000_000.0], [False], []

    def handle(request: httpx.Request) -> httpx.Response:
        asked.append(request)
        if down[0]:
            raise httpx.ConnectError("no route", request=request)
        return httpx.Response(200, json=FAIRSHARING_JSON)

    api = FairsharingClient(
        httpx.Client(transport=httpx.MockTransport(handle)),
        cache=memory_cache(lambda: clock[0]),
        now=lambda: clock[0],
    )
    advisor = agent(
        repositories=re3data,
        databases=FairsharingLive(api=api),
        databases_fallback=FairsharingSnapshot(),
    )
    needs = RepositoryNeeds(mandated=[RepositoryRef(name="UK Data Service")])

    live = _cited(invoke(runs_dir, needs, advisor))
    cached = _cited(invoke(runs_dir, needs, advisor))
    assert len(asked) == 1
    clock[0] += 10**7
    down[0] = True
    stale = _cited(invoke(runs_dir, needs, advisor))

    assert live.snapshot_ref == "fairsharing:live"
    assert cached.snapshot_ref == "fairsharing:cache"
    assert stale.snapshot_ref is not None
    assert (
        stale.snapshot_ref.startswith("fairsharing:cache")
        and stale.snapshot_ref != "fairsharing:cache"
    )
    assert live.retrieved_at == cached.retrieved_at == stale.retrieved_at
    assert live.content_hash == cached.content_hash == stale.content_hash
