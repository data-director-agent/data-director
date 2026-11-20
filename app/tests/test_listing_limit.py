"""Slow listings cannot take the worker threads a turn needs (#1258): they run in a pool of
their own, and past its queue a listing is answered `503` with `Retry-After` at once."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.testclient import TestClient
from support import configure_env, dist_dir, new_governance

from dd_app.deployment_view import DeploymentView
from dd_app.listing_limit import (
    ListingBusyError,
    ListingConfigError,
    ListingLimiter,
)
from dd_app.project_service import ProjectService
from dd_app.reads import Reads
from dd_app.routes import runs
from dd_app.routes.common import Deps
from dd_harness.listing import Page


def test_listings_are_limited_from_the_environment() -> None:
    assert ListingLimiter.from_env({}) == ListingLimiter(8, 16, 2)
    env = {
        "DD_APP_LISTING_THREADS": "3",
        "DD_APP_LISTING_QUEUE": "0",
        "DD_APP_LISTING_RETRY_S": "5",
    }
    assert ListingLimiter.from_env(env) == ListingLimiter(3, 0, 5)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("DD_APP_LISTING_THREADS", "0"),
        ("DD_APP_LISTING_THREADS", "many"),
        ("DD_APP_LISTING_QUEUE", "-1"),
        ("DD_APP_LISTING_RETRY_S", "0"),
    ],
)
def test_a_limit_that_is_not_a_whole_number_in_range_is_refused(variable: str, value: str) -> None:
    with pytest.raises(ListingConfigError, match=variable):
        ListingLimiter.from_env({variable: value})


def test_slow_listings_leave_the_shared_threads_free_and_the_rest_are_refused() -> None:
    limiter = ListingLimiter(threads=2, queue=1, retry_after=7)
    release = threading.Event()
    running = threading.Semaphore(0)

    def slow() -> str:
        running.release()
        release.wait(timeout=30)
        return "listed"

    async def scenario() -> list[str]:
        held = [asyncio.create_task(limiter.run(slow)) for _ in range(3)]  # 2 running, 1 waiting
        await asyncio.to_thread(running.acquire)
        await asyncio.to_thread(running.acquire)
        await asyncio.sleep(0.05)
        # What a turn needs is still there: the shared pool takes work at once.
        assert await asyncio.wait_for(run_in_threadpool(lambda: "turn"), timeout=5) == "turn"
        with pytest.raises(ListingBusyError) as busy:
            await limiter.run(slow)
        assert busy.value.retry_after == 7
        release.set()
        return await asyncio.gather(*held)

    assert asyncio.run(scenario()) == ["listed"] * 3


@pytest.fixture
def deps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Deps]:
    configure_env(monkeypatch, tmp_path)
    for governance in new_governance():
        yield Deps(
            governance=governance,
            projects=ProjectService.over(governance),
            reads=Reads(governance),
            deployment=DeploymentView(governance),
            web_dist=dist_dir(tmp_path),
            identity={},
            listing=ListingLimiter(threads=1, queue=0, retry_after=3),
        )


def test_a_listing_with_every_thread_busy_is_answered_503_with_retry_after(deps: Deps) -> None:
    release, entered = threading.Event(), threading.Event()
    real = deps.reads.runs

    def slow(*args: Any, **kwargs: Any) -> Page:
        entered.set()
        release.wait(timeout=30)
        return real(*args, **kwargs)

    object.__setattr__(deps, "reads", replace(deps.reads))
    object.__setattr__(deps.reads, "runs", slow)
    client = TestClient(Starlette(routes=runs.routes(deps)))
    first: list[int] = []
    holder = threading.Thread(target=lambda: first.append(client.get("/api/runs").status_code))
    holder.start()
    try:
        assert entered.wait(timeout=10)
        busy = client.get("/api/runs")
        assert busy.status_code == 503
        assert busy.headers["retry-after"] == "3"
        assert busy.headers["content-type"].startswith("application/problem+json")
        assert busy.json()["type"].endswith("/listing-busy")
    finally:
        release.set()
        holder.join(timeout=30)
    assert first == [200]
    assert client.get("/api/runs").status_code == 200
