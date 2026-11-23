"""Who may use a deployment that signs people in (docs/specs/policy-and-identity.md, Admission).

The profile's `access` key says whether a deployment admits anyone the provider vouches for
(`admit: anyone`, the default) or only the people it lists (`admit: listed`), and names people it
refuses whatever else lists them (`block`). People are named by principal identifier, as the
authentication boundary records them, and matched on that alone, never on a name.

A deployment's stewards and administrators (`dd_harness.stewardship`) are admitted under
`listed` without being listed again; a blocked one is refused like anyone else.

The way in checks admission when a person signs in and again on every request
(`dd_harness.sessions.SessionAuthenticator`), so a person blocked after signing in loses their
session at their next request. A run already going finishes for whoever started it.

This module reads the key; `dd_harness.policy.Profile` holds what it reads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from dd_harness.stewardship import principals
from dd_sdk.contract.models import Principal

# Whom a deployment admits: anyone the provider vouches for, or only the people it lists.
ADMIT = ("anyone", "listed")
ACCESS_KEYS = frozenset({"admit", "allow", "block"})


@dataclass(frozen=True)
class Access:
    """The profile's `access` key, as read."""

    admit: str = "anyone"
    allow: frozenset[str] = frozenset()
    block: frozenset[str] = frozenset()


def parse(value: Any) -> Access:
    """Read the profile's `access` key. Raises `TypeError` or `ValueError` with what is wrong,
    which the profile reports as malformed."""
    if value is None:
        return Access()
    if not isinstance(value, dict):
        raise TypeError("access is a mapping with admit, and allow or block lists")
    if unknown := sorted(set(value) - ACCESS_KEYS):
        raise ValueError(
            f"access has keys nothing enforces: {', '.join(unknown)}; "
            f"it has {', '.join(sorted(ACCESS_KEYS))}"
        )
    admit = value.get("admit", "anyone")
    if admit not in ADMIT:
        raise ValueError(f"access.admit is {admit!r}; it is one of {', '.join(ADMIT)}")
    allow = principals(value.get("allow"), "access.allow")
    block = principals(value.get("block"), "access.block")
    if allow and admit == "anyone":
        # A list nothing reads would tell an operator the deployment is closed when it is not.
        raise ValueError("access.allow is read only with admit: listed; this profile admits anyone")
    if both := sorted(allow & block):
        raise ValueError(f"access lists {', '.join(both)} in both allow and block")
    return Access(str(admit), allow, block)


@dataclass(frozen=True)
class Admission:
    """Whom a way in admits: a person the deployment's issuer vouched for, whom the profile
    admits (`admits` is the profile's `Profile.admits`). Given to `dd_harness.signin.SignIn` as
    its `admit`."""

    issuer: str
    admits: Callable[[str], bool]

    def __call__(self, principal: Principal) -> bool:
        return principal.vouched_by == self.issuer and self.admits(principal.principal_id)
