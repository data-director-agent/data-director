"""A profile's `model_accounts` (docs/specs/model-accounts.md, The profile): whether people may, or
must, use their own model account, whether the deployment pays for someone who has none, and which
providers, base URLs and model mappings a person's own account may use. `dd_harness.policy` reads
it into `Profile.model_accounts`."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from dd_sdk.agent import ModelUse
from dd_sdk.model_grant import Account, origin

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
