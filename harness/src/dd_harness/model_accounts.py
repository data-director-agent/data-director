"""Whose model account pays for an invocation, as the conductor applies the profile's
`model_accounts` (docs/specs/model-accounts.md).

`bypasses_broker` says whether an agent would call a model outside the model broker while the
profile lets people's own accounts pay, which the conductor refuses; `model_grant` mints the grant
an invocation of a model-backed remote agent is sent. Only the conductor calls them.
"""

from __future__ import annotations

from dd_harness import policy
from dd_harness.model_grants import GrantMinter, GrantRequest
from dd_harness.registry import Registered
from dd_harness.remote import RemoteAgent
from dd_sdk.contract.models import InvocationRequest, Principal
from dd_sdk.model_grant import Account
from dd_sdk.security_log import SecurityEvent, emit


def bypasses_broker(profile: policy.Profile, agent: Registered) -> bool:
    """Whether `agent` may call a model without the model broker while the profile lets
    people's own accounts pay (docs/specs/model-accounts.md, invariant 14).

    Only the operator's statement in the registry's configuration (`model_broker`) counts,
    never the agent's card. An agent run in this process is never sent a grant, so it cannot
    call through the broker.
    """
    if profile.model_accounts.own == "off" or not agent.spec.models:
        return False
    return not (isinstance(agent, RemoteAgent) and agent.model_broker)


def model_grant(
    profile: policy.Profile,
    minter: GrantMinter | None,
    agent: Registered,
    request: InvocationRequest,
    acting_for: Principal,
) -> str | None:
    """The model grant for this invocation, or None (docs/specs/model-accounts.md).

    Minted afresh for every invocation of a remote agent whose card declares `models`,
    delegated children included, and only here: a request cannot carry one. It expires with
    the agent's transport timeout, and is passed to the agent alone: it never enters the
    envelope, a span or a store (invariant 6).
    """
    spec = agent.spec
    if minter is None or not spec.models or not isinstance(agent, RemoteAgent):
        return None
    # Who pays is the profile's decision, never the agent's or the request's; the broker
    # enforces what the grant says.
    accounts = profile.model_accounts
    account = accounts.account
    own = account is not Account.DEPLOYMENT
    minted = minter.mint(
        GrantRequest(
            agent_id=spec.agent_id,
            invocation_id=request.invocation_id,
            models=(model.model for model in spec.models),
            account=account,
            acting_for=acting_for,
            lifetime_s=agent.timeout_s,
            providers=accounts.provider_names if own else (),
            base_urls=accounts.base_urls if own else (),
            model_map=accounts.model_map(spec.models) if own else None,
        )
    )
    # The security event names the grant's terms, never the grant (docs/specs/security.md).
    emit(
        SecurityEvent.GRANT_MINTED,
        outcome="success",
        service="harness",
        principal=acting_for.principal_id,
        agent_id=spec.agent_id,
        invocation_id=request.invocation_id,
        models=[model.model for model in spec.models],
        account=account.value,
    )
    return minted
