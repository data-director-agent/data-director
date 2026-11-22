"""FAIRsharing policy records read through the live route's local cache (#327): a record read
again within its time to live asks nothing, and one assembled from two answers is cited under the
weaker of them."""

from __future__ import annotations

import json
from pathlib import Path

import httpx

from dd_agent_advisor_policy.live import PolicyLive
from dd_sdk.registry import Query, provenance
from dd_sdk.registry.caching import memory_cache
from dd_sdk.registry.fairsharing import FairsharingClient

DATA = Path(__file__).with_name("data")
PUBLIC = json.loads((DATA / "FAIRsharing.e081af.public.json").read_text(encoding="utf-8"))
API = json.loads((DATA / "FAIRsharing.e081af.api.json").read_text(encoding="utf-8"))
RECORD = "FAIRsharing.e081af"


class Fake:
    """FAIRsharing's two hosts; either can be taken down."""

    def __init__(self) -> None:
        self.t = 1_000_000.0
        self.down: set[str] = set()
        self.asked: list[str] = []

    def __call__(self, req: httpx.Request) -> httpx.Response:
        if req.url.path == "/users/sign_in":
            return httpx.Response(200, json={"jwt": "token"})
        self.asked.append(req.url.path)
        if req.url.host in self.down:
            raise httpx.ConnectError("no route", request=req)
        if req.url.host == "fairsharing.org":
            return httpx.Response(200, json=PUBLIC)
        if req.url.path.startswith("/search"):
            return httpx.Response(200, json={"data": [API["data"]]})
        return httpx.Response(200, json=API)

    def live(self) -> PolicyLive:
        api = FairsharingClient(
            httpx.Client(transport=httpx.MockTransport(self)),
            login="me",
            password="secret",
            cache=memory_cache(lambda: self.t),
            now=lambda: self.t,
        )
        return PolicyLive(api=api)


def _cite(live: PolicyLive, read: str) -> tuple[str, bool]:
    with provenance.observed() as origins:
        if read == "fetch":
            live.fetch(RECORD)
        else:
            live.search(Query(text="University of Sheffield"))
    ref = origins.ref(RECORD, live.snapshot_ref())
    return ref.label, ref.stale


def test_a_record_read_again_is_cited_from_the_cache() -> None:
    fake = Fake()
    live = fake.live()
    label = live.snapshot_ref().label
    cache = provenance.cache_label(label)
    assert _cite(live, "fetch") == (label, False)
    assert _cite(live, "fetch") == (cache, False)
    assert _cite(live, "search") == (label, False)
    assert _cite(live, "search") == (cache, False)
    assert len(fake.asked) == 3  # the public route, the API record and one search


def test_a_record_from_two_answers_is_cited_under_the_weaker() -> None:
    fake = Fake()
    live = fake.live()
    _cite(live, "fetch")
    fake.t += 10**7
    fake.down = {"api.fairsharing.org"}
    assert _cite(live, "fetch") == (provenance.cache_label(live.snapshot_ref().label), True)
