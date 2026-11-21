"""Transports: how a deposit package reaches a repository (docs/specs/deposit.md, Packagers and
transports).

A transport that sends anything through a platform's API is registered under the entry-point group
`dd.transports`, by the identifier an override's `deposit` block names:

    [project.entry-points."dd.transports"]
    zenodo = "dd_harness.transports.zenodo:TRANSPORT"

What the harness needs of one is how to render the approved DataCite record into the item the
platform's API takes (its `format`), and the file name the RO-Crate package takes in the draft. The
API calls themselves are made by the deposit broker, which holds the person's token
(`dd_sdk.deposit_grant`), never by the harness. The `manual` transport sends nothing and is not
registered: a repository without a `deposit` block is deposited to by hand.

An identifier names one protocol for good (invariant 17); a registered transport that the profile
does not offer is refused like an unknown one, before anything is rendered, sent or recorded.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from typing import Any

GROUP = "dd.transports"
# The transport every deployment offers: a person uploading the package by hand.
MANUAL = "manual"


class TransportError(Exception):
    """A transport cannot be found or loaded, or is registered wrongly."""


@dataclass(frozen=True)
class RenderedItem:
    """The platform item rendered from the approved DataCite record: its exact bytes, which are
    kept by their digest and sent, and the record's properties the mapping could not place, which
    the outcome names rather than dropping them silently."""

    content: bytes
    unplaced: tuple[str, ...] = ()


@dataclass(frozen=True)
class Transport:
    """A transport that sends a rendered item and the RO-Crate package through a platform's API.

    - `name`: the identifier an override's `deposit.transport` names;
    - `format`: the format of the item it carries, such as `zenodo-deposit`;
    - `media_type`: the item's media type;
    - `render`: from the approved DataCite record's attributes and the connector's `target` to
      the item. It never sees a credential and makes no call.
    """

    name: str
    format: str
    media_type: str
    render: Callable[[Mapping[str, Any], str | None], RenderedItem] = field(repr=False)


def discover() -> dict[str, Transport]:
    """Every transport the installed packages register, by name."""
    found: dict[str, Transport] = {}
    for point in entry_points(group=GROUP):
        where = point.dist.name if point.dist else point.value
        try:
            transport = point.load()
        # Whatever a transport's module raises on import is reported as that transport's.
        except Exception as exc:  # noqa: BLE001
            raise TransportError(f"{where}: cannot load transport {point.name!r}: {exc}") from None
        if not isinstance(transport, Transport):
            raise TransportError(f"{where}: {point.value} is not a dd_sdk.transports.Transport")
        if transport.name != point.name:
            raise TransportError(
                f"{where}: entry point {point.name!r} names a transport called {transport.name!r}"
            )
        if transport.name == MANUAL or transport.name in found:
            raise TransportError(f"{where}: transport {transport.name!r} is registered twice")
        found[transport.name] = transport
    return dict(sorted(found.items()))
