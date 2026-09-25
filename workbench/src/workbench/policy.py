"""The policy gate (ADR-0003, ADR-0017). Small on purpose; the complexity is in the profile content.

The profile belongs to the deployment. The operator names one file when the conductor is built
(`DD_PROFILE`, or `--profile` on the CLI); a request cannot name one. The profile, not the
agent, states each enabled agent's action class: the class an agent declares on its card is
checked against it, never trusted on its own.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROFILES_DIR = Path(__file__).resolve().parents[2] / "profiles"
DEFAULT_PROFILE = PROFILES_DIR / "default.yaml"

# The whole vocabulary. A key outside it is refused: a key nothing enforces would tell a steward
# a rule is in force when it is not (ADR-0017).
PROFILE_KEYS = frozenset(
    {"profile_id", "version", "description", "agents", "actions_requiring_approval"}
)


class PolicyError(Exception):
    """A profile could not be loaded or is malformed. Configuration error, so it raises."""


@dataclass(frozen=True)
class Profile:
    profile_id: str
    version: int
    agents: dict[str, str]  # agent_id -> the action class the steward assigns it
    actions_requiring_approval: frozenset[str]
    digest: str  # SHA-256 of the file's bytes
    source: str = ""

    @property
    def ref(self) -> str:
        """What an envelope records as `policy_bundle_ref`."""
        return f"profile:{self.profile_id}@v{self.version}"

    @classmethod
    def from_mapping(cls, data: dict[str, Any], source: str, digest: str) -> Profile:
        unknown = sorted(set(data) - PROFILE_KEYS)
        if unknown:
            raise PolicyError(
                f"profile {source!r} has keys nothing enforces: {', '.join(unknown)}; "
                f"the vocabulary is {', '.join(sorted(PROFILE_KEYS))}"
            )
        try:
            agents = data.get("agents") or {}
            if not isinstance(agents, dict):
                raise TypeError("agents must map each agent_id to an action class")
            return cls(
                profile_id=str(data["profile_id"]),
                version=int(data.get("version", 1)),
                agents={str(k): str(v) for k, v in agents.items()},
                actions_requiring_approval=frozenset(data.get("actions_requiring_approval") or []),
                digest=digest,
                source=source,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyError(f"profile {source!r} is malformed: {exc}") from exc


def load_profile(path: Path) -> Profile:
    """Load the deployment's profile. The path is the operator's, never a caller's."""
    if not path.is_file():
        raise PolicyError(f"profile not found at {path}")
    raw = path.read_bytes()
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise PolicyError(f"profile {str(path)!r} is not a mapping")
    return Profile.from_mapping(data, source=str(path), digest=hashlib.sha256(raw).hexdigest())


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    requires_approval: bool
    reason: str
    # Why a refused agent was refused: "not-enabled" or "action-class-mismatch".
    refusal: str | None = None


def gate(profile: Profile, agent_id: str, declared_action_class: str) -> GateDecision:
    """May this agent run, and does the class the profile gives it require approval?"""
    assigned = profile.agents.get(agent_id)
    if assigned is None:
        return GateDecision(False, False, f"agent {agent_id!r} not enabled", "not-enabled")
    if declared_action_class != assigned:
        return GateDecision(
            False,
            False,
            f"agent {agent_id!r} declares action class {declared_action_class!r}; "
            f"profile {profile.profile_id!r} assigns it {assigned!r}",
            "action-class-mismatch",
        )
    if assigned in profile.actions_requiring_approval:
        return GateDecision(
            True,
            True,
            f"action class {assigned!r} requires approval under {profile.profile_id!r}",
        )
    return GateDecision(True, False, "permitted")
