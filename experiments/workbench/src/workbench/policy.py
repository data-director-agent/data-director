"""The policy gate (ADR-0003). Small on purpose; the complexity is in the profile content."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"
PROFILE_SCHEME = "profile:"


class PolicyError(Exception):
    """A profile could not be loaded or is malformed. Configuration error, so it raises."""


@dataclass(frozen=True)
class Profile:
    profile_id: str
    version: int
    agents_enabled: frozenset[str]
    actions_requiring_approval: frozenset[str]
    approved_repositories: tuple[str, ...] = ()
    pid_systems: tuple[str, ...] = ()
    registries: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any], source: str) -> Profile:
        try:
            return cls(
                profile_id=str(data["profile_id"]),
                version=int(data.get("version", 1)),
                agents_enabled=frozenset(data.get("agents_enabled") or []),
                actions_requiring_approval=frozenset(data.get("actions_requiring_approval") or []),
                approved_repositories=tuple(data.get("approved_repositories") or []),
                pid_systems=tuple(data.get("pid_systems") or []),
                registries=dict(data.get("registries") or {}),
                source=source,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyError(f"profile {source!r} is malformed: {exc}") from exc


def load_profile(ref: str, profiles_dir: Path = PROFILES_DIR) -> Profile:
    """`profile:<id>` resolves to <profiles_dir>/<id>.yaml; anything else is a path."""
    path = (
        profiles_dir / f"{ref[len(PROFILE_SCHEME) :]}.yaml"
        if ref.startswith(PROFILE_SCHEME)
        else Path(ref)
    )
    if not path.is_file():
        raise PolicyError(f"profile {ref!r} not found at {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise PolicyError(f"profile {ref!r} is not a mapping")
    return Profile.from_mapping(data, source=str(path))


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    requires_approval: bool
    reason: str


def gate(profile: Profile, agent_id: str, action_class: str) -> GateDecision:
    """Answer the two questions the gate exists for. Nothing else."""
    if agent_id not in profile.agents_enabled:
        return GateDecision(False, False, f"agent {agent_id!r} not in agents_enabled")
    if action_class in profile.actions_requiring_approval:
        return GateDecision(
            True,
            True,
            f"action class {action_class!r} requires approval under {profile.profile_id!r}",
        )
    return GateDecision(True, False, "permitted")
