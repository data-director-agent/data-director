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

from dd_harness.footprint import FootprintTable
from dd_sdk.agent import ModelUse, Setting
from dd_sdk.model_grant import Account, origin

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
    }
)

# The classes of project content (docs/specs/projects.md, invariant 8): the inventory of the data
# files, documentation (a document's text, or what a person wrote about one), the facts
# researchers kept from their public ORCID records, and the facts people decided about the project
# (its funders, required repositories, which files go in, sensitivity and licence), which hold
# structured values only, never a person's words.
CONTENT_CLASSES = ("inventory", "documentation", "researcher", "decisions")
# What may be given to an agent whose card declares a hosted model, where the profile does not say.
DEFAULT_HOSTED_MODELS = frozenset({"inventory", "decisions"})


class PolicyError(Exception):
    """A profile could not be loaded or is malformed. Configuration error, so it raises."""


# `model_accounts` (docs/specs/model-accounts.md, The profile). `own`: whether people may, or must,
# use their own model account; `fallback`: whether the deployment pays for someone who has none.
OWN_SETTINGS = ("off", "allowed", "required")
FALLBACK_SETTINGS = ("deployment", "none")
# The providers a person's own account may be with: those the broker can serve. Only an
# `openai-compatible` account names a base URL, and it must: it has no endpoint of its own. Every
# other provider's account calls the provider's own endpoint.
COMPATIBLE = "openai-compatible"
OWN_PROVIDERS = ("anthropic", "openai", "gemini", COMPATIBLE)
_MODEL_ACCOUNTS_KEYS = frozenset({"own", "fallback", "providers"})
_PROVIDER_KEYS = frozenset({"provider", "base_urls", "models"})
_BASE_URL_KEYS = frozenset({"url", "local"})
_MODEL_KEYS = frozenset({"declared", "model", "tools"})


@dataclass(frozen=True)
class OwnBaseUrl:
    """An origin a person's own account may name as its base URL. `local` says the steward
    declares the endpoint local, so it does not count as `hosted` (`hosted_models`)."""

    origin: str
    local: bool = False


@dataclass(frozen=True)
class OwnModel:
    """One entry of a provider's model map: the model a provider serves (`model`) in place of one
    an agent's card may declare (`declared`), and whether it serves tool calls (`tools`), as the
    steward states (docs/specs/model-accounts.md, The model map)."""

    declared: str
    model: str
    tools: bool = False


@dataclass(frozen=True)
class OwnProvider:
    """A provider a person's own account may be with, the base URLs it may name, and its model
    map. Without a base URL the account calls the provider itself, which is always `hosted`."""

    provider: str
    base_urls: tuple[OwnBaseUrl, ...] = ()
    models: tuple[OwnModel, ...] = ()


@dataclass(frozen=True)
class ModelAccounts:
    """Whose account pays for model calls (docs/specs/model-accounts.md, The profile). The
    conductor turns it into each grant's account, and the broker enforces the grant."""

    own: str = "off"
    fallback: str | None = None
    providers: tuple[OwnProvider, ...] = ()

    @property
    def account(self) -> Account:
        """The account every grant under this profile names."""
        if self.own == "off":
            return Account.DEPLOYMENT
        if self.own == "allowed" and self.fallback == "deployment":
            return Account.OWN_OR_DEPLOYMENT
        return Account.OWN

    @property
    def provider_names(self) -> tuple[str, ...]:
        return tuple(p.provider for p in self.providers)

    @property
    def base_urls(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(u.origin for p in self.providers for u in p.base_urls))

    def model_map(self, uses: Iterable[ModelUse]) -> dict[str, dict[str, str]]:
        """The model map for a grant to an agent whose card declares `uses`: for each provider,
        each mapping of a model the card declares, leaving out one that does not serve tool calls
        where the card relies on them. Empty while own accounts are off."""
        if self.own == "off":
            return {}
        needs_tools = {u.model: u.tools for u in uses}
        model_map: dict[str, dict[str, str]] = {}
        for provider in self.providers:
            mapped = {
                m.declared: m.model
                for m in provider.models
                if m.declared in needs_tools and (m.tools or not needs_tools[m.declared])
            }
            if mapped:
                model_map[provider.provider] = mapped
        return model_map

    @property
    def hosted(self) -> bool:
        """Whether a person's own account may call a model the profile does not declare local:
        the provider's own endpoint, or a base URL without `local: true`."""
        if self.own == "off":
            return False
        # A provider's own endpoint is always hosted, and an account with no base URL calls it.
        return any(not p.base_urls or not all(u.local for u in p.base_urls) for p in self.providers)

    @classmethod
    def from_value(cls, value: Any) -> ModelAccounts:
        """Read the profile's `model_accounts`. Raises `TypeError` or `ValueError` for anything a
        steward could misread as being in force: a profile holds only what is enforced."""
        if value is None:
            return cls()
        if not isinstance(value, dict):
            raise TypeError("model_accounts must be a mapping")
        _only(value, _MODEL_ACCOUNTS_KEYS, "model_accounts")
        written_own = value.get("own", "off")
        # YAML 1.1 reads an unquoted `off` as false, and a steward writes `own: off`.
        own = "off" if written_own is False else str(written_own)
        if own not in OWN_SETTINGS:
            raise ValueError(
                f"model_accounts.own is {own!r}; it is one of {', '.join(OWN_SETTINGS)}"
            )
        if own == "off":
            # Nothing would apply a fallback or a provider list, so neither may be written.
            if extra := sorted(set(value) & {"fallback", "providers"}):
                raise ValueError(
                    f"model_accounts.own is off, so {' and '.join(extra)} would not be enforced"
                )
            return cls()
        fallback = value.get("fallback")
        if fallback not in FALLBACK_SETTINGS:
            raise ValueError(
                f"model_accounts.fallback must be one of {', '.join(FALLBACK_SETTINGS)} "
                "when own accounts are on"
            )
        if own == "required" and fallback == "deployment":
            raise ValueError(
                "model_accounts.own is required, so fallback cannot be deployment; use none"
            )
        written = value.get("providers")
        if not isinstance(written, list) or not written:
            raise ValueError("model_accounts.providers must list at least one provider")
        providers = tuple(_provider(entry) for entry in written)
        if len({p.provider for p in providers}) != len(providers):
            raise ValueError("model_accounts.providers names a provider more than once")
        return cls(own=own, fallback=str(fallback), providers=providers)


def _only(mapping: dict[str, Any], keys: frozenset[str], where: str) -> None:
    if unknown := sorted(set(map(str, mapping)) - keys):
        raise ValueError(
            f"{where} has keys nothing enforces: {', '.join(unknown)}; "
            f"they are {', '.join(sorted(keys))}"
        )


def _provider(entry: Any) -> OwnProvider:
    if not isinstance(entry, dict):
        raise TypeError("each of model_accounts.providers must be a mapping")
    _only(entry, _PROVIDER_KEYS, "a model_accounts provider")
    name = str(entry.get("provider") or "")
    if name not in OWN_PROVIDERS:
        raise ValueError(
            f"model_accounts names provider {name!r}; a person's own account may be with "
            f"{', '.join(OWN_PROVIDERS)}"
        )
    urls = entry.get("base_urls") or []
    if not isinstance(urls, list):
        raise TypeError("model_accounts base_urls must be a list")
    # The broker sends a base URL only for an openai-compatible account, so base URLs on any other
    # provider would be rules nothing enforces, and would make its endpoint look local.
    if name == COMPATIBLE and not urls:
        raise ValueError(
            f"model_accounts provider {COMPATIBLE} must list base_urls: it has no endpoint "
            "of its own"
        )
    if name != COMPATIBLE and urls:
        raise ValueError(
            f"model_accounts provider {name} calls its own endpoint, so base_urls would not be "
            f"enforced; only {COMPATIBLE} names them"
        )
    base_urls: list[OwnBaseUrl] = []
    for url in urls:
        if not isinstance(url, dict):
            raise TypeError("each model_accounts base URL must be a mapping with a url")
        _only(url, _BASE_URL_KEYS, "a model_accounts base URL")
        local = url.get("local", False)
        if not isinstance(local, bool):
            raise TypeError("a model_accounts base URL's local must be true or false")
        try:
            base_urls.append(OwnBaseUrl(origin(str(url.get("url") or "")), local))
        except ValueError as exc:
            raise ValueError(f"model_accounts base URL: {exc}") from None
    return OwnProvider(name, tuple(base_urls), _models(name, entry.get("models") or []))


def _models(provider: str, written: Any) -> tuple[OwnModel, ...]:
    if not isinstance(written, list):
        raise TypeError(f"model_accounts provider {provider}'s models must be a list")
    models: list[OwnModel] = []
    for entry in written:
        if not isinstance(entry, dict):
            raise TypeError(
                f"each of model_accounts provider {provider}'s models must be a mapping with "
                "declared and model"
            )
        _only(entry, _MODEL_KEYS, f"a model_accounts provider {provider} model")
        declared, model = entry.get("declared"), entry.get("model")
        if not isinstance(declared, str) or not declared or not isinstance(model, str) or not model:
            raise ValueError(
                f"each of model_accounts provider {provider}'s models must name both declared "
                "and model"
            )
        tools = entry.get("tools", False)
        if not isinstance(tools, bool):
            raise TypeError("a model_accounts model's tools must be true or false")
        models.append(OwnModel(declared, model, tools))
    if len({m.declared for m in models}) != len(models):
        raise ValueError(f"model_accounts provider {provider} maps a declared model more than once")
    return tuple(models)


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
    model_accounts: ModelAccounts = ModelAccounts()
    # agent_id -> {setting: value}: the options the steward sets for each agent, which the gate
    # checks against those the agent's card declares (docs/specs/policy-and-identity.md).
    agent_settings: dict[str, dict[str, str]] = field(default_factory=dict)
    # The figures the conductor estimates each run's model energy and cost from (P14, C17;
    # docs/specs/disclosure.md, Footprint). None: nothing is estimated.
    model_footprint: FootprintTable | None = None

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
            hosted = data.get("hosted_models", sorted(DEFAULT_HOSTED_MODELS))
            if not isinstance(hosted, list):
                raise TypeError("hosted_models must list classes of project content")
            if wrong := sorted({str(c) for c in hosted} - set(CONTENT_CLASSES)):
                raise ValueError(
                    f"hosted_models names {', '.join(map(repr, wrong))}; "
                    f"the classes of project content are {', '.join(CONTENT_CLASSES)}"
                )
            return cls(
                profile_id=str(data["profile_id"]),
                version=int(data.get("version", 1)),
                agents={str(k): str(v) for k, v in agents.items()},
                actions_requiring_approval=frozenset(data.get("actions_requiring_approval") or []),
                digest=digest,
                source=source,
                orchestrator=None if orchestrator is None else str(orchestrator),
                description=str(data.get("description") or "").strip(),
                hosted_models=frozenset(str(c) for c in hosted),
                model_accounts=ModelAccounts.from_value(data.get("model_accounts")),
                agent_settings=_agent_settings(data.get("agent_settings"), agents),
                model_footprint=FootprintTable.from_value(data.get("model_footprint")),
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


def withheld(profile: Profile, hostings: Iterable[str], given: Iterable[str]) -> list[str]:
    """The classes of project content in `given` that may not go to an agent whose models are
    hosted as `hostings`, sorted; empty if the agent calls no hosted model
    (docs/specs/projects.md, invariant 8).

    Where the profile lets a person's own account pay, a model-backed agent's call may go to that
    account's endpoint, which counts as `hosted` unless the profile declares it local
    (docs/specs/model-accounts.md, The profile)."""
    declared = set(hostings)
    if declared and profile.model_accounts.hosted:
        declared.add("hosted")
    if "hosted" not in declared:
        return []
    return sorted(set(given) - profile.hosted_models)
