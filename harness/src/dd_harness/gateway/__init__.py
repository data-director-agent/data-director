"""The harness's tool gateway (docs/specs/agents.md, Tools): `config` reads the deployment's list
of MCP servers, `core` holds the grants and records what tools return, `upstream` calls the
servers and `endpoint` is the MCP endpoint agents call. All but `config` need the harness's
`gateway` extra, so a way in mounts the endpoint through `routes`, which imports it only for a
deployment that lists servers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from starlette.routing import Route

if TYPE_CHECKING:
    from dd_harness.gateway.core import Gateway


def routes(gateway: Gateway | None) -> list[Route]:
    """The gateway's MCP endpoint (`dd_sdk.wire.GATEWAY_PATH`), or no route without a gateway."""
    if gateway is None:
        return []
    from dd_harness.gateway.endpoint import gateway_routes

    return gateway_routes(gateway)
