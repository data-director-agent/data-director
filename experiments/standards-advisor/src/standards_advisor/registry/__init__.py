"""Registry access (§7.2)."""

from __future__ import annotations

from standards_advisor.errors import ConfigError
from standards_advisor.registry.base import (
    RegistryClient,
    RegistryRecord,
    RegistrySearchResult,
    RegistryTerm,
)
from standards_advisor.registry.empty import EmptyRegistry
from standards_advisor.registry.fairsharing import FairsharingRegistry

__all__ = [
    "EmptyRegistry",
    "FairsharingRegistry",
    "RegistryClient",
    "RegistryRecord",
    "RegistrySearchResult",
    "RegistryTerm",
    "get_registry",
]

_ROUTES: dict[str, type[EmptyRegistry] | type[FairsharingRegistry]] = {
    "empty": EmptyRegistry,
    "fairsharing": FairsharingRegistry,
}


def get_registry(route: str) -> RegistryClient:
    """Build the registry client named by configuration.

    Swapping route is a configuration change, not a rewrite — that is the point of one
    interface in front of them (§7.2).
    """
    try:
        return _ROUTES[route]()
    except KeyError:
        known = ", ".join(sorted(_ROUTES))
        raise ConfigError(f"unknown registry route {route!r}; known routes: {known}") from None
