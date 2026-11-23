"""The policy gate (docs/specs/policy-and-identity.md). Small on purpose; the complexity is in the
profile content.

The profile belongs to the deployment. The operator names one file when the conductor is built
(`DD_PROFILE`, or `--profile` on the CLI); a request cannot name one. The profile, not the
agent, states each enabled agent's action class: the class an agent declares on its card is
checked against it, never trusted on its own.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from dd_harness.content_classes import CONTENT_CLASSES as CONTENT_CLASSES
from dd_harness.content_classes import DEFAULT_HOSTED_MODELS, DEFAULT_REMOTE_TOOL_CONTENT, classes
from dd_harness.content_classes import tool_servers as granted_servers
from dd_harness.footprint import FootprintTable
from dd_harness.institution_repositories import parse as institution_repositories
from dd_harness.institution_storage import parse as institution_storage
from dd_harness.profile_model_accounts import ModelAccounts
from dd_harness.stewardship import DeploymentRoles, Stewardship, deployment_roles, principals
from dd_harness.stewardship import parse as stewardship
from dd_sdk.agent import Setting
from dd_sdk.contract.facts import InstitutionStorage
from dd_sdk.contract.models import InstitutionRepository
from dd_sdk.security_log import SecurityEvent, emit

# The whole vocabulary. A key outside it is refused: a key nothing enforces would tell a steward
# a rule is in force when it is not (docs/specs/policy-and-identity.md).
PROFILE_KEYS = frozenset(
    {
        "profile_id",
        "version",
        "description",
        "agents",
        "actions_requiring_approval",
        "orchestrator",
        "hosted_models",
        "model_accounts",
        "agent_settings",
        "model_footprint",
        "tool_servers",
        "remote_tool_content",
        "attached_documents",
        "deposit_transports",
        "institution_repositories",
        "institution_storage",
        "stewardship",
        "administrators",
    }
)
# Whether people may attach documents to a project (docs/specs/projects.md, Documentation).
ATTACHED_DOCUMENTS = ("allowed", "refused")


class PolicyError(Exception):
    """A profile could not be loaded or is malformed. Configuration error, so it raises."""


class DocumentsRefusedError(ValueError):
    """The profile refuses attached documents, and a document was attached: a refusal of the
    request, made before anything is kept (`check_attached_document`)."""


def _deposit_transports(value: Any) -> frozenset[str]:
    """The transports a profile offers for depositing through an API. `manual` may be listed and
    is always offered; whether a listed one is installed is checked when a deposit is approved."""
    if value is None:
        return frozenset()
    if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
        raise TypeError("deposit_transports must list transport names")
    return frozenset(value) - {"manual"}


@dataclass(frozen=True)
class Profile:
    profile_id: str
    version: int
    agents: dict[str, str]  # agent_id -> the action class the steward assigns it
    actions_requiring_approval: frozenset[str]
    digest: str  # SHA-256 of the file's bytes
    source: str = ""
    # The agent a person converses with first (docs/specs/app.md). The app sends conversation turns
    # to it and to no other; None means the deployment offers no conversation.
    orchestrator: str | None = None
    # What the steward says the profile is for, shown beside its rules (docs/specs/app.md).
    description: str = ""
    # The classes of project content that may be given to an agent whose card declares a
    # `hosted` model (docs/specs/projects.md, invariant 8).
    hosted_models: frozenset[str] = DEFAULT_HOSTED_MODELS
    # Whose account pays for model calls (docs/specs/model-accounts.md). Off unless written.
    model_accounts: ModelAccounts = field(default_factory=ModelAccounts)
    # agent_id -> {setting: value}: the options the steward sets for each agent, which the gate
    # checks against those the agent's card declares (docs/specs/policy-and-identity.md).
    agent_settings: dict[str, dict[str, str]] = field(default_factory=dict)
    # The figures the conductor estimates each run's model energy and cost from (P14, C17;
    # docs/specs/disclosure.md, Footprint). None: nothing is estimated.
    model_footprint: FootprintTable | None = None
    # agent_id -> the MCP servers the tool gateway lets it call (docs/specs/agents.md, Tools).
    # An agent with no entry calls none.
    tool_servers: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # The classes of project content that may be given to an agent granted a `remote` server.
    remote_tool_content: frozenset[str] = DEFAULT_REMOTE_TOOL_CONTENT
    # Whether people may attach documents to a project, one of ATTACHED_DOCUMENTS.
    attached_documents: str = "allowed"
    # The transports the harness may deposit a draft through, beside the manual one that every
    # deployment offers (docs/specs/deposit.md, invariant 17). None unless written.
    deposit_transports: frozenset[str] = frozenset()
    # The repositories the deployment names as its institution's, by a registry's identifier,
    # with what it vouches for of each (dd_harness.institution_repositories). None unless written.
    institution_repositories: tuple[InstitutionRepository, ...] = ()
    # The storage services the deployment names as its institution's, for keeping data while a
    # project runs, with what it vouches for of each (dd_harness.institution_storage).
    institution_storage: tuple[InstitutionStorage, ...] = ()
    # The deployment's steward teams, and who administers it: deployment roles
    # (docs/specs/stewardship.md, invariant 1; dd_harness.stewardship). None unless written.
    stewardship: Stewardship = field(default_factory=Stewardship)
    administrators: frozenset[str] = frozenset()

    @property
    def refuses_documents(self) -> bool:
        """Whether the profile refuses attached documents altogether."""
        return self.attached_documents == "refused"

    def roles_of(self, principal_id: str) -> DeploymentRoles:
        """The deployment roles this profile gives `principal_id` (dd_harness.stewardship)."""
        return deployment_roles(self.stewardship, self.administrators, principal_id)

    def record_loaded(self, service: str) -> None:
        """Record in the security log that `service` holds people to this profile. Roles change
        only with the profile, so this event, with the profile's version, is where a role
        change shows (docs/specs/stewardship.md, invariant 1)."""
        emit(
            SecurityEvent.PROFILE_LOADED,
            outcome="success",
            service=service,
            profile_id=self.profile_id,
            profile_version=self.version,
        )

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
            orchestrator = data.get("orchestrator")
            if orchestrator is not None and str(orchestrator) not in agents:
                raise ValueError(
                    f"orchestrator {orchestrator!r} is not one of the agents the profile enables"
                )
            documents = data.get("attached_documents", "allowed")
            if documents not in ATTACHED_DOCUMENTS:
                raise ValueError(
                    f"attached_documents is {documents!r}; it is one of "
                    f"{', '.join(ATTACHED_DOCUMENTS)}"
                )
            ref = f"profile:{data['profile_id']}@v{int(data.get('version', 1))}"
            return cls(
                profile_id=str(data["profile_id"]),
                version=int(data.get("version", 1)),
                agents={str(k): str(v) for k, v in agents.items()},
                actions_requiring_approval=frozenset(data.get("actions_requiring_approval") or []),
                digest=digest,
                source=source,
                orchestrator=None if orchestrator is None else str(orchestrator),
                description=str(data.get("description") or "").strip(),
                hosted_models=classes(data, "hosted_models", DEFAULT_HOSTED_MODELS),
                model_accounts=ModelAccounts.from_value(data.get("model_accounts")),
                agent_settings=_agent_settings(data.get("agent_settings"), agents),
                model_footprint=FootprintTable.from_value(data.get("model_footprint")),
                tool_servers=granted_servers(data.get("tool_servers"), agents),
                remote_tool_content=classes(
                    data, "remote_tool_content", DEFAULT_REMOTE_TOOL_CONTENT
                ),
                attached_documents=str(documents),
                deposit_transports=_deposit_transports(data.get("deposit_transports")),
                institution_repositories=institution_repositories(
                    data.get("institution_repositories"), ref
                ),
                institution_storage=institution_storage(data.get("institution_storage"), ref),
                stewardship=stewardship(data.get("stewardship")),
                administrators=principals(data.get("administrators"), "administrators"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PolicyError(f"profile {source!r} is malformed: {exc}") from exc


def _agent_settings(value: Any, agents: dict[Any, Any]) -> dict[str, dict[str, str]]:
    """Read the profile's `agent_settings`: each enabled agent's settings, as strings. Whether the
    agent declares them is checked at invocation, against its card (`gate`)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("agent_settings must map each agent_id to its settings")
    out: dict[str, dict[str, str]] = {}
    for agent_id, settings in value.items():
        if str(agent_id) not in {str(a) for a in agents}:
            raise ValueError(
                f"agent_settings names {agent_id!r}, which is not one of the agents the profile "
                "enables"
            )
        if not isinstance(settings, dict):
            raise TypeError(f"agent_settings for {agent_id!r} must map each setting to a value")
        for name, setting in settings.items():
            # YAML reads on/off/yes/no as booleans and bare numbers as numbers; a setting's
            # choices are strings, so ask for the value to be written as one.
            if not isinstance(setting, str):
                raise TypeError(
                    f"agent_settings {agent_id}.{name} is {setting!r}; write the value as a "
                    "quoted string"
                )
        out[str(agent_id)] = {str(k): v for k, v in settings.items()}
    return out


def check_attached_document(profile: Profile) -> None:
    """Raise `DocumentsRefusedError` where the profile refuses attached documents. A way in calls
    it before it keeps anything a request attached (docs/specs/projects.md, Documentation)."""
    if profile.refuses_documents:
        raise DocumentsRefusedError(
            "This deployment does not keep attached documents: its profile refuses them. Give "
            "what the document says in your message instead."
        )


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
    # Why a refused agent was refused: "not-enabled", "action-class-mismatch" or
    # "setting-not-declared".
    refusal: str | None = None
    # The agent's settings for this invocation, when it may run: its card's defaults overlaid by
    # the profile's `agent_settings`.
    settings: Mapping[str, str] = field(default_factory=dict)


def gate(
    profile: Profile,
    agent_id: str,
    declared_action_class: str,
    declared_settings: Mapping[str, Setting] | None = None,
) -> GateDecision:
    """May this agent run, with which settings, and does the class the profile gives it require
    approval? A setting the profile gives an agent whose card does not declare it, or a value
    outside its choices, refuses the agent: a setting nothing would apply must not look as if it
    were in force."""
    assigned = profile.agents.get(agent_id)
    if assigned is None:
        return GateDecision(
            allowed=False,
            requires_approval=False,
            reason=f"agent {agent_id!r} not enabled",
            refusal="not-enabled",
        )
    if declared_action_class != assigned:
        return GateDecision(
            allowed=False,
            requires_approval=False,
            reason=f"agent {agent_id!r} declares action class {declared_action_class!r}; "
            f"profile {profile.profile_id!r} assigns it {assigned!r}",
            refusal="action-class-mismatch",
        )
    declared = declared_settings or {}
    settings = {name: s.default for name, s in declared.items()}
    for name, value in profile.agent_settings.get(agent_id, {}).items():
        offered = declared.get(name)
        if offered is None or value not in offered.choices:
            accepts = (
                f"it accepts {', '.join(map(repr, offered.choices))}"
                if offered is not None
                else (
                    f"its settings are {', '.join(map(repr, sorted(declared)))}"
                    if declared
                    else "it declares no settings"
                )
            )
            return GateDecision(
                allowed=False,
                requires_approval=False,
                reason=f"profile {profile.profile_id!r} sets {agent_id}'s {name!r} to {value!r}; "
                f"{accepts}",
                refusal="setting-not-declared",
            )
        settings[name] = value
    if assigned in profile.actions_requiring_approval:
        return GateDecision(
            allowed=True,
            requires_approval=True,
            reason=f"action class {assigned!r} requires approval under {profile.profile_id!r}",
            settings=settings,
        )
    return GateDecision(
        allowed=True, requires_approval=False, reason="permitted", settings=settings
    )


def withheld(
    profile: Profile, hostings: Iterable[str], given: Iterable[str], *, remote_tools: bool = False
) -> list[str]:
    """The classes of project content in `given` that may not go to an agent whose models are
    hosted as `hostings`, or that is granted a `remote` MCP server (`remote_tools`), sorted; empty
    if the agent calls neither (docs/specs/projects.md, invariant 8;
    docs/specs/policy-and-identity.md).

    Where the profile lets a person's own account pay, a model-backed agent's call may go to that
    account's endpoint, which counts as `hosted` unless the profile declares it local
    (docs/specs/model-accounts.md, The profile)."""
    declared = set(hostings)
    if declared and profile.model_accounts.hosted:
        declared.add("hosted")
    out = set(given) - profile.hosted_models if "hosted" in declared else set()
    if remote_tools:
        out |= set(given) - profile.remote_tool_content
    return sorted(out)
