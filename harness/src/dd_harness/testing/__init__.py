"""The harness's test kit: scripted doubles and a conductor over them, for the harness's own
tests, for agent packages, and for any way in to the harness (the workbench, the app).

`in_process(agent)` serves an agent object with `dd_sdk.serve` on an in-memory httpx ASGI
transport and returns the `RemoteAgent` the registry would build from its card, so a test
exercises the real A2A wire (request, metadata, spans, spec extension) without a network or a
second process. `make_conductor` does this for every agent it is given, so a harness test runs
an agent the way a deployment runs it.

The conductor `make_conductor` builds also serves its own A2A routes
(`dd_harness.transport.a2a`) in memory and gives each agent a delegate client bound to them, so a
delegation agent's call back to the conductor (ADR-0012) crosses the real wire too. Nothing here
needs the workbench (ADR-0022).

`FakeIdentityProvider` stands in for an OpenID Connect provider such as ORCID (ADR-0029): a local
signing key, its published keys, and ID tokens built to order, so that a test of sign-in needs no
network and no real account.

`AbstainingStub` abstains unconditionally under the fixed id `stub.abstain`, which the test profiles
name, so a test can exercise the gate, the store and the non-success path without scripting
anything. `ScriptedAgent` is a generic double whose specification and behaviour are set per test. It
emits the spans a test asks for, then returns (or raises) what it was given, so harness and linter
behaviour can be pinned for each grounding mode without a retrieval backend or a model. Nothing
here knows about any real agent.

The doubles read and return `Probe*` classes of their own, declared in `../schema/doubles.yaml`.
The conductor knows them only from the doubles' cards, as it knows every real agent's classes
(ADR-0019). The test profiles are in `profiles/`.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from a2a.client import ClientConfig, create_client
from a2a.helpers import new_data_part
from a2a.types import Message as A2AMessage
from a2a.types import Role, SendMessageRequest
from joserfc import jwt
from joserfc.jwk import KeySet, RSAKey
from pydantic import Field
from starlette.applications import Starlette

from dd_harness.conductor import Conductor
from dd_harness.identity import (
    BearerTokenAuthenticator,
    IssuerKeys,
    OidcProvider,
    OperatorAssertion,
)
from dd_harness.policy import load_profile
from dd_harness.registry import Registry
from dd_harness.remote import RemoteAgent
from dd_harness.store import RunStore
from dd_harness.transport.a2a import a2a_routes
from dd_sdk import serve
from dd_sdk.agent import Agent, AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    Frozen,
    Grounded,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Message,
    Outcome,
    OutcomeStatus,
    Principal,
    ReasonCode,
    Reply,
    new_invocation_id,
    to_document,
)
from dd_sdk.delegate import Delegated, HarnessDelegate
from dd_sdk.evidence import (
    DOCUMENT_CANONICALISATION,
    HASH_ALGORITHM,
    INPUT_CANONICALISATION,
    content_hash,
)
from dd_sdk.tracing import chat_span, retrieval_span

__all__ = [
    "HARNESS_URL",
    "PERMISSIVE",
    "PROFILES_DIR",
    "RESTRICTIVE",
    "SOURCE_A",
    "SOURCE_B",
    "SPECS",
    "TEST_PRINCIPAL",
    "AbstainingStub",
    "Behaviour",
    "Chat",
    "FakeIdentityProvider",
    "ProbeCheck",
    "ProbeClaim",
    "ProbeProfile",
    "ProbeRecord",
    "ProbeReview",
    "Retrieve",
    "ScriptedAgent",
    "asgi_client_factory",
    "claim",
    "fact_check_over",
    "grant_token",
    "in_process",
    "input_evidence",
    "input_ref",
    "make_conductor",
    "message",
    "profile",
    "record",
    "reply_over",
    "request",
    "review_of_input",
]

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
PERMISSIVE = PROFILES_DIR / "test-permissive.yaml"
RESTRICTIVE = PROFILES_DIR / "test-restrictive.yaml"

# Whom test invocations act for (ADR-0018): the ORCID documentation's example researcher, so a
# stored test run never names a real person.
TEST_PRINCIPAL = Principal(
    principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry"
)

# --- A fake identity provider (ADR-0029) ------------------------------------------------------

# RSA modulus size for the fake provider's key: the smallest that RS256 verifiers accept.
FAKE_KEY_BITS = 2048
FAKE_TOKEN_LIFETIME_S = 600


def _signing_key(kid: str) -> RSAKey:
    return RSAKey.generate_key(FAKE_KEY_BITS, parameters={"kid": kid, "use": "sig", "alg": "RS256"})


@dataclass
class FakeIdentityProvider:
    """An OpenID Connect provider in memory: it signs ID tokens with a local key and publishes
    that key, as ORCID does at its `jwks_uri`. The issuer defaults to ORCID's sandbox, so the
    principals it yields have the form a development deployment records."""

    issuer: str = "https://sandbox.orcid.org"
    client_id: str = "APP-TESTCLIENT0000"
    key: RSAKey = field(default_factory=lambda: _signing_key("fake-1"))
    fetches: int = 0

    @property
    def provider(self) -> OidcProvider:
        return OidcProvider(issuer=self.issuer, client_id=self.client_id)

    def jwks(self, issuer: str = "") -> dict[str, Any]:
        """The published keys: what `IssuerKeys` would fetch from the issuer."""
        self.fetches += 1
        return dict(KeySet([self.key]).as_dict(private=False))

    def keys(self) -> IssuerKeys:
        return IssuerKeys(self.issuer, fetch=self.jwks)

    def authenticator(self) -> BearerTokenAuthenticator:
        return BearerTokenAuthenticator(self.provider, self.keys())

    def rotate(self, kid: str) -> None:
        """Sign with a new key from now on, as a provider rotating its keys does."""
        self.key = _signing_key(kid)

    def id_token(
        self,
        sub: str = "0000-0002-1825-0097",
        *,
        name: str | None = "Josiah Carberry",
        nonce: str | None = None,
        issued_at: int | None = None,
        lifetime_s: int = FAKE_TOKEN_LIFETIME_S,
        audience: str | list[str] | None = None,
        issuer: str | None = None,
        key: RSAKey | None = None,
        **claims: Any,
    ) -> str:
        """An ID token as the provider would issue it; each argument changes one claim, so a
        test can build the token it means to refuse."""
        iat = int(time.time()) if issued_at is None else issued_at
        body: dict[str, Any] = {
            "iss": issuer or self.issuer,
            "aud": self.client_id if audience is None else audience,
            "sub": sub,
            "iat": iat,
            "exp": iat + lifetime_s,
            "auth_time": iat,
            **({"name": name} if name is not None else {}),
            **({"nonce": nonce} if nonce is not None else {}),
            **claims,
        }
        signer = key or self.key
        return jwt.encode({"alg": "RS256", "kid": signer.kid}, body, signer)


# --- The doubles' own classes (schema/doubles.yaml) -----------------------------------------


class ProbeRecord(Frozen):
    schema_class: Literal["ProbeRecord"] = "ProbeRecord"
    identifier: str | None = None
    title: str | None = None
    licence: str | None = None
    creators: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)


class ProbeClaim(Frozen):
    schema_class: Literal["ProbeClaim"] = "ProbeClaim"
    text: str


class ProbeProfile(Frozen):
    schema_class: Literal["ProbeProfile"] = "ProbeProfile"
    title: str | None = None


class ProbeReview(Grounded):
    schema_class: Literal["ProbeReview"] = "ProbeReview"
    score: float | None = None


class ProbeCheck(Grounded):
    schema_class: Literal["ProbeCheck"] = "ProbeCheck"
    rationale: str
    rationale_derivation: Derivation


Behaviour = AgentResult | Exception | Callable[[InvocationRequest, RunContext], AgentResult]


@dataclass(frozen=True)
class Retrieve:
    """Emit a retrieval span for one source document before the result is produced."""

    source_id: str
    document: dict[str, Any]

    @property
    def content_hash(self) -> str:
        return content_hash(self.document, DOCUMENT_CANONICALISATION)

    def ref(self) -> GroundingRef:
        return GroundingRef(source_id=self.source_id, content_hash=self.content_hash)

    def evidence(self) -> EvidenceItem:
        return EvidenceItem(
            source_id=self.source_id,
            retrieved_at=datetime.now(UTC),
            hash_algorithm=HASH_ALGORITHM,
            canonicalisation=DOCUMENT_CANONICALISATION,
            content_hash=self.content_hash,
        )


@dataclass(frozen=True)
class Chat:
    """Emit a chat span (a model call) before the result is produced."""

    model_id: str = "fake-model"


SPECS: dict[GroundingMode, AgentSpec] = {
    GroundingMode.RETRIEVAL: AgentSpec(
        agent_id="fake.retrieval",
        version="0",
        description="Scripted retrieval-mode agent.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeClaim),),
        grounding_mode=GroundingMode.RETRIEVAL,
        payload=ClassSchema.of(ProbeCheck),
    ),
    GroundingMode.INPUT_ONLY: AgentSpec(
        agent_id="fake.input-only",
        version="0",
        description="Scripted input-only agent.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeRecord),),
        grounding_mode=GroundingMode.INPUT_ONLY,
        payload=ClassSchema.of(ProbeReview),
    ),
    GroundingMode.NONE: AgentSpec(
        agent_id="fake.none",
        version="0",
        description="Scripted deterministic agent.",
        action_class="advise",
        accepts=(ClassSchema.of(ProbeRecord), ClassSchema.of(ProbeProfile)),
        grounding_mode=GroundingMode.NONE,
        payload=ClassSchema.of(ProbeReview),
    ),
    GroundingMode.DELEGATION: AgentSpec(
        agent_id="fake.delegation",
        version="0",
        description="Scripted delegation-mode agent.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.DELEGATION,
        payload=ClassSchema.of(Reply),
    ),
}


class ScriptedAgent:
    def __init__(
        self,
        mode: GroundingMode,
        behaviour: Behaviour,
        steps: Iterable[Retrieve | Chat] = (),
        **spec_overrides: Any,
    ) -> None:
        self.spec = replace(SPECS[mode], **spec_overrides)
        self.behaviour = behaviour
        self.steps = list(steps)
        self.calls = 0

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        self.calls += 1
        for step in self.steps:
            if isinstance(step, Retrieve):
                with retrieval_span(ctx.tracer, step.source_id, step.content_hash):
                    pass
            else:
                with chat_span(ctx.tracer, step.model_id):
                    pass
        if isinstance(self.behaviour, Exception):
            raise self.behaviour
        if isinstance(self.behaviour, AgentResult):
            return self.behaviour
        return self.behaviour(request, ctx)


class AbstainingStub:
    """Abstains unconditionally with `capability_not_implemented`. It accepts the core's
    `Message` (ADR-0019) and declares grounding mode `none`."""

    spec = AgentSpec(
        agent_id="stub.abstain",
        version="0.3.0",
        description="Abstains unconditionally; exercises the non-success path.",
        action_class="advise",
        accepts=(ClassSchema.of(Message),),
        grounding_mode=GroundingMode.NONE,
        payload=None,
    )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.ABSTAINED,
                reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                statement=(
                    "This agent is a stub and abstains unconditionally. No registry was searched "
                    "and no model was called."
                ),
            )
        )


# --- Results a scripted agent can return ------------------------------------------------------


def input_ref(ctx: RunContext) -> GroundingRef:
    return GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)


def input_evidence(ctx: RunContext) -> EvidenceItem:
    return EvidenceItem(
        source_id=ctx.input_ref,
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=INPUT_CANONICALISATION,
        content_hash=ctx.input_hash,
    )


def review_of_input(request: InvocationRequest, ctx: RunContext) -> AgentResult:
    """A succeeded ProbeReview grounded on the input, as an input_only/none agent should."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Reviewed."),
        payload=ProbeReview(score=1.0, grounded_on=[input_ref(ctx)]),
        evidence=[input_evidence(ctx)],
    )


def fact_check_over(*sources: Retrieve) -> AgentResult:
    """A succeeded ProbeCheck grounded on exactly the given sources."""
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Checked."),
        payload=ProbeCheck(
            rationale="Scripted.",
            rationale_derivation=Derivation.TEMPLATE,
            grounded_on=[s.ref() for s in sources],
        ),
        evidence=[s.evidence() for s in sources],
    )


def grant_token(ctx: RunContext) -> str:
    """The grant token behind a delegation agent's `delegate`, for a test that presents it to
    the conductor directly instead of through `delegate`."""
    assert isinstance(ctx.delegate, HarnessDelegate), "the agent was not issued a grant"
    return ctx.delegate.grant.token


def reply_over(ctx: RunContext, *delegated: Delegated) -> AgentResult:
    """A succeeded Reply grounded on the input and the given child envelopes."""
    text = "; ".join(f"{d.envelope.agent_id}: {d.envelope.outcome.statement}" for d in delegated)
    return AgentResult(
        outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Relayed."),
        payload=Reply(
            reply_text=text or "Nothing delegated.",
            reply_derivation=Derivation.TEMPLATE,
            grounded_on=[input_ref(ctx), *(d.ref for d in delegated)],
        ),
        evidence=[input_evidence(ctx), *(d.evidence for d in delegated)],
    )


SOURCE_A = Retrieve("src:a", {"source_id": "src:a", "text": "Alpha."})
SOURCE_B = Retrieve("src:b", {"source_id": "src:b", "text": "Beta."})


# --- Harness helpers --------------------------------------------------------------------------


def asgi_client_factory(app: Any) -> Callable[[str, float], httpx.AsyncClient]:
    """An httpx client factory bound to one ASGI app, for `RemoteAgent` and `Registry`."""

    def factory(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=base_url, timeout=timeout_s
        )

    return factory


HARNESS_URL = "http://harness.test"


def send_to_harness(
    app: Any,
    base_url: str,
    request: InvocationRequest,
    metadata: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Any:
    """Send `request` to the conductor's A2A routes served by `app` at `base_url`, with the
    message metadata and HTTP headers given, and return the task that came back."""

    async def send() -> Any:
        async with asgi_client_factory(app)(base_url, 30.0) as hc:
            hc.headers.update(headers or {})
            client = await create_client(
                agent=base_url, client_config=ClientConfig(streaming=False, httpx_client=hc)
            )
            message = A2AMessage(
                role=Role.ROLE_USER,
                parts=[new_data_part(to_document(request))],
                message_id=new_invocation_id(),
                metadata=metadata or {},
            )
            last = None
            async for response in client.send_message(SendMessageRequest(message=message)):
                last = response
            return getattr(last, "task", None)

    return asyncio.run(send())


def in_process(
    agent: Agent,
    timeout_s: float = 30.0,
    delegate_client_factory: Callable[[str, float], httpx.AsyncClient] | None = None,
) -> RemoteAgent:
    """Serve `agent` in memory and return the `RemoteAgent` built from its card.

    `delegate_client_factory` is the client a delegation agent calls the harness back with.
    """
    base_url = f"http://{agent.spec.agent_id}.agents.test"
    kwargs: dict[str, Any] = {}
    if delegate_client_factory is not None:
        kwargs["delegate_client_factory"] = delegate_client_factory
    app = serve.app(agent, base_url=base_url, **kwargs)
    return RemoteAgent.from_url(
        base_url, timeout_s=timeout_s, client_factory=asgi_client_factory(app)
    )


def make_conductor(
    runs_dir: Path,
    *agents: Agent,
    crate: bool = False,
    remote: bool = True,
    profile: Path = PERMISSIVE,
) -> Conductor:
    """A conductor over `agents`, each reached over in-process A2A unless `remote` is False,
    governed by the institutional profile at `profile`.

    A remote conductor also serves its own A2A routes in memory at `HARNESS_URL` and sets them
    as the delegation callback, so delegation runs over the wire as it does in production. Those
    routes act for `TEST_PRINCIPAL`; a test invokes the conductor with `acting_for=TEST_PRINCIPAL`.
    """
    harness_app: dict[str, Any] = {}

    def harness_client(base_url: str, timeout_s: float) -> httpx.AsyncClient:
        return asgi_client_factory(harness_app["app"])(base_url, timeout_s)

    registry = Registry.from_agents(
        in_process(a, delegate_client_factory=harness_client) if remote else a for a in agents
    )
    conductor = Conductor(
        registry=registry,
        store=RunStore(runs_dir),
        profile=load_profile(profile),
        write_crate=crate,
    )
    if remote:
        _card, routes = a2a_routes(conductor, OperatorAssertion(TEST_PRINCIPAL), HARNESS_URL)
        harness_app["app"] = Starlette(routes=routes)
        conductor.harness_url = HARNESS_URL
    return conductor


def message(text: str = "hello") -> Message:
    return Message(message_text=text)


def record() -> ProbeRecord:
    return ProbeRecord(
        identifier="https://doi.org/10.15131/shef.data.00000000",
        title="Soil chemistry survey",
        licence="https://creativecommons.org/licenses/by/4.0/",
        creators=["Example Researcher"],
    )


def claim() -> ProbeClaim:
    return ProbeClaim(text="A DOI does not change when the object moves.")


def profile() -> ProbeProfile:
    return ProbeProfile(title="Soil chemistry survey")


def request(agent_id: str, input: Frozen | None = None) -> InvocationRequest:
    return InvocationRequest(agent_id=agent_id, input=input or record())
