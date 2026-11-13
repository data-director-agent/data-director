"""Where the broker may send a person's key (docs/specs/model-accounts.md, Security).

A person's own account may name a custom base URL: an OpenAI-compatible endpoint (TODO(#811)).
Before the broker sends a key there, `check_base_url`:

1. requires `https`, a host, and no user information, query or fragment;
2. requires the URL's origin to be on the operator's allow-list;
3. resolves the host and refuses it if any address it resolves to is private, loopback,
   link-local, reserved, multicast or otherwise not global, unless the operator listed the origin
   as a private endpoint as well;
4. returns a `Target` pinned to the address it checked, so that the call connects to that address
   and a second lookup cannot send it somewhere else. TLS still verifies the certificate against
   the host name.

The deployment's own base URL (the LiteLLM gateway, `DD_BROKER_DEPLOYMENT_BASE_URL`) and the
provider's fixed URL are set by the operator, not by a person, and do not pass through here.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from dd_sdk.model_grant import origin as grant_origin

Resolver = Callable[[str, int], Sequence[str]]


class BaseUrlRefused(ValueError):
    """A base URL the broker will not send a key to. The message names the rule, not the URL."""


@dataclass(frozen=True)
class Target:
    """Where one call goes: `url` (with the checked address in place of the host, when pinned),
    and the host name to send as `Host` and to verify TLS against."""

    url: str
    host: str | None = None
    port: int | None = None

    @property
    def headers(self) -> dict[str, str]:
        if not self.host:
            return {}
        return {"host": self.host if self.port in (None, 443) else f"{self.host}:{self.port}"}

    @property
    def extensions(self) -> dict[str, str]:
        return {"sni_hostname": self.host} if self.host else {}


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def origin(url: str) -> str:
    """`https://host[:port]`, lower case, with the default port left out. Raises `BaseUrlRefused`
    for anything that is not a plain `https` URL."""
    try:
        return grant_origin(url)
    except ValueError as exc:
        raise BaseUrlRefused(str(exc)) from None


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_base_url(
    url: str,
    allowed: Collection[str],
    *,
    private: Collection[str] = (),
    resolve: Resolver = system_resolver,
) -> Target:
    """The pinned target for `url`, or `BaseUrlRefused`. `allowed` and `private` are origins as
    the operator configured them (`DD_BROKER_ALLOWED_BASE_URLS`, `DD_BROKER_PRIVATE_BASE_URLS`)."""
    wanted = origin(url)
    allowed_origins = {origin(entry) for entry in allowed}
    private_origins = {origin(entry) for entry in private}
    if wanted not in allowed_origins | private_origins:
        raise BaseUrlRefused("the base URL is not on the operator's allow-list")
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    port = parts.port or 443
    try:
        addresses = list(resolve(host, port))
    except OSError as exc:
        raise BaseUrlRefused("the base URL's host does not resolve") from exc
    if not addresses:
        raise BaseUrlRefused("the base URL's host does not resolve")
    if wanted not in private_origins and not all(_is_public(a) for a in addresses):
        raise BaseUrlRefused("the base URL resolves to a private or reserved address")
    pinned = addresses[0]
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        # Already an address: nothing to pin.
        return Target(url=url.strip().rstrip("/"))
    shown = f"[{pinned}]" if ":" in pinned else pinned
    netloc = shown if parts.port is None else f"{shown}:{parts.port}"
    pinned_url = urlunsplit(("https", netloc, parts.path.rstrip("/"), "", ""))
    return Target(url=pinned_url, host=host, port=parts.port)
