"""Agents and the conductor served in memory over A2A.

`in_process(agent)` serves an agent object with `dd_sdk.serve` on an in-memory httpx ASGI
transport and returns the `RemoteAgent` the registry would build from its card, so a test
exercises the real A2A wire (request, metadata, spans, spec extension) without a network or a
second process. `make_conductor` does this for every agent it is given, so a harness test runs
an agent the way a deployment runs it.

The conductor `make_conductor` builds also serves its own A2A routes
(`dd_harness.transport.a2a`) in memory and gives each agent a delegate client bound to them, so a
delegation agent's call back to the conductor (ADR-0012) crosses the real wire too.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_data_part
from a2a.types import Message as A2AMessage
from a2a.types import Role, SendMessageRequest
from starlette.applications import Starlette

from dd_harness.conductor import Conductor
from dd_harness.identity import OperatorAssertion
from dd_harness.policy import load_profile
from dd_harness.registry import Registry
from dd_harness.remote import RemoteAgent
from dd_harness.store import RunStore
from dd_harness.testing.fixtures import PERMISSIVE, TEST_PRINCIPAL
from dd_harness.transport.a2a import a2a_routes
from dd_sdk import serve
from dd_sdk.agent import Agent
from dd_sdk.contract.models import InvocationRequest, new_invocation_id, to_document


def asgi_client_factory(app: Any) -> Callable[[str, float], httpx.AsyncClient]:
    """An httpx client factory bound to one ASGI app, for `RemoteAgent` and `Registry`."""

    def factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url, timeout=timeout_s
        )

    return factory


HARNESS_URL = "http://harness.test"


def send_to_harness(
    app: Any,
    base_url: str,
    request: InvocationRequest,
    metadata: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Send `request` to the conductor's A2A routes served by `app` at `base_url`, with the
    message metadata and HTTP headers given, and return the task that came back."""

    async def send() -> Any:
        async with asgi_client_factory(app)(base_url, 30.0) as hc:
            hc.headers.update(headers or {})
            client = await create_client(
                agent=base_url, client_config=ClientConfig(streaming=False, httpx_client=hc)
            )
            message = A2AMessage(
                role=Role.ROLE_USER,
                parts=[new_data_part(to_document(request))],
                message_id=new_invocation_id(),
                metadata=metadata or {},
            )
            last = None
            async for response in client.send_message(SendMessageRequest(message=message)):
                last = response
            return getattr(last, "task", None)

    return asyncio.run(send())


def in_process(
    agent: Agent,
    timeout_s: float = 30.0,
    delegate_client_factory: Callable[[str, float], httpx.AsyncClient] | None = None,
) -> RemoteAgent:
    """Serve `agent` in memory and return the `RemoteAgent` built from its card.

    `delegate_client_factory` is the client a delegation agent calls the harness back with.
    """
    base_url = f"http://{agent.spec.agent_id}.agents.test"
    kwargs: dict[str, Any] = {}
    if delegate_client_factory is not None:
        kwargs["delegate_client_factory"] = delegate_client_factory
    app = serve.app(agent, base_url=base_url, **kwargs)
    return RemoteAgent.from_url(
        base_url, timeout_s=timeout_s, client_factory=asgi_client_factory(app)
    )


def make_conductor(
    runs_dir: Path,
    *agents: Agent,
    crate: bool = False,
    remote: bool = True,
    profile: Path = PERMISSIVE,
) -> Conductor:
    """A conductor over `agents`, each reached over in-process A2A unless `remote` is False,
    governed by the institutional profile at `profile`.

    A remote conductor also serves its own A2A routes in memory at `HARNESS_URL` and sets them
    as the delegation callback, so delegation runs over the wire as it does in production. Those
    routes act for `TEST_PRINCIPAL`; a test invokes the conductor with `acting_for=TEST_PRINCIPAL`.
    """
    harness_app: dict[str, Any] = {}

    def harness_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return asgi_client_factory(harness_app["app"])(base_url, timeout_s)

    registry = Registry.from_agents(
        in_process(a, delegate_client_factory=harness_client) if remote else a for a in agents
    )
    conductor = Conductor(
        registry=registry,
        store=RunStore(runs_dir),
        profile=load_profile(profile),
        write_crate=crate,
    )
    if remote:
        _card, routes = a2a_routes(conductor, OperatorAssertion(TEST_PRINCIPAL), HARNESS_URL)
        harness_app["app"] = Starlette(routes=routes)
        conductor.harness_url = HARNESS_URL
    return conductor
