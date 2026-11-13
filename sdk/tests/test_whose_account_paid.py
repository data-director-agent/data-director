"""Each model call records whose account paid, as the broker reports it, and a run whose person's
own account cannot be used ends abstained, not as an exception (docs/specs/model-accounts.md,
invariants 9 and 10)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx2 as httpx
import pytest

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, RunContext
from dd_sdk.contract.classes import ClassSchema
from dd_sdk.contract.models import (
    GroundingMode,
    InvocationRequest,
    Message,
    ModelAccount,
    Outcome,
    OutcomeStatus,
    ReasonCode,
)
from dd_sdk.credentials import ModelEndpoint
from dd_sdk.model import call
from dd_sdk.model_account import refusal
from dd_sdk.model_anthropic import AnthropicModel, anthropic_client
from dd_sdk.model_grant import HEADER_ACCOUNT, HEADER_REASON, META_MODEL_GRANT
from dd_sdk.prompts import ModelCallLog
from dd_sdk.tracing import ATTR_MODEL_ACCOUNT, CHAT
from dd_sdk.wire import reply_from_document

CREDENTIAL = "dd-broker-credential-0123456789"
BROKER = "http://broker.test:8790"
GRANT = "eyJhbGciOiJSUzI1NiJ9.grant.signature"

ANSWER = {
    "id": "msg_1",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "ok"}],
    "stop_reason": "end_turn",
    "stop_sequence": None,
    "usage": {"input_tokens": 3, "output_tokens": 1},
}

# The broker's refusals of a person's own account: the status and the `X-DD-Reason` it sends
# (`dd_broker.reasons`), and the reason code the run ends with.
REFUSALS = [
    (403, "model-account-missing", ReasonCode.MODEL_ACCOUNT_MISSING),
    (403, "model-account-rejected", ReasonCode.MODEL_ACCOUNT_REJECTED),
    (429, "model-account-limit", ReasonCode.MODEL_ACCOUNT_LIMIT),
]
ERROR_TYPE = {403: "permission_error", 429: "rate_limit_error"}


class Broker:
    """Answers each call in turn as the broker would: `own` or `deployment` paid, or a refusal
    given as `(status, reason)`."""

    def __init__(self, *answers: ModelAccount | tuple[int, str] | None) -> None:
        self.answers: Iterator[ModelAccount | tuple[int, str] | None] = iter(answers)

    def __call__(self, request: httpx.Request) -> httpx.Response:
        answer = next(self.answers)
        if isinstance(answer, tuple):
            status, reason = answer
            return httpx.Response(
                status,
                # The client would otherwise retry a 429 after a pause.
                headers={HEADER_REASON: reason, "x-should-retry": "false"},
                json={"type": "error", "error": {"type": ERROR_TYPE[status], "message": reason}},
            )
        headers = {HEADER_ACCOUNT: answer.value} if answer is not None else {}
        return httpx.Response(200, headers=headers, json=ANSWER)


def client(broker: Broker, *, brokered: bool = True) -> Any:
    endpoint = (
        ModelEndpoint(CREDENTIAL, BROKER + "/anthropic") if brokered else ModelEndpoint(CREDENTIAL)
    )
    return anthropic_client(
        endpoint, http_client=httpx.Client(transport=httpx.MockTransport(broker))
    )


SPEC = AgentSpec(
    agent_id="test.accounted",
    version="0.0.0",
    description="An agent that calls a model twice through the broker.",
    action_class="advise",
    accepts=(ClassSchema.of(Message),),
    grounding_mode=GroundingMode.NONE,
    payload=None,
)


class Twice:
    """Calls the model twice, once through the SDK's `call` and once with the client directly,
    as the advisors do."""

    spec = SPEC

    def __init__(self, broker: Broker, *, brokered: bool = True) -> None:
        self.client = client(broker, brokered=brokered)

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        log = ModelCallLog("anthropic")
        call(
            AnthropicModel("claude-test", client=self.client),
            ctx,
            system="Be brief.",
            messages=[{"role": "user", "content": "one"}],
            calls=log,
        )
        self.client.messages.create(
            model="claude-test", max_tokens=16, messages=[{"role": "user", "content": "two"}]
        )
        log.record({"messages": [{"role": "user", "content": "two"}]}, "claude-test")
        return AgentResult(
            outcome=Outcome(status=OutcomeStatus.SUCCEEDED, statement="Done."),
            model_calls=log.calls,
            prompts=log.prompts,
        )


def run(agent: Twice) -> tuple[AgentResult, tuple[dict[str, Any], ...]]:
    request = InvocationRequest(agent_id=SPEC.agent_id, input=Message(message_text="Hello."))
    return reply_from_document(serve.run_traced(agent, request, {META_MODEL_GRANT: GRANT}))


def chat_accounts(spans: tuple[dict[str, Any], ...]) -> list[Any]:
    return [s["attributes"].get(ATTR_MODEL_ACCOUNT) for s in spans if s["name"] == CHAT]


def test_each_call_records_whose_account_the_broker_said_paid() -> None:
    result, spans = run(Twice(Broker(ModelAccount.OWN, ModelAccount.DEPLOYMENT)))
    assert [c.model_account for c in result.model_calls] == [
        ModelAccount.OWN,
        ModelAccount.DEPLOYMENT,
    ]
    assert chat_accounts(spans)[0] == ModelAccount.OWN.value


def test_a_call_without_the_broker_is_paid_for_by_the_deployment() -> None:
    result, spans = run(Twice(Broker(None, None), brokered=False))
    assert {c.model_account for c in result.model_calls} == {ModelAccount.DEPLOYMENT}
    assert chat_accounts(spans) == [ModelAccount.DEPLOYMENT.value]


def test_a_call_does_not_inherit_the_payer_of_the_call_before() -> None:
    # The second answer names no payer, so the second call is not the person's.
    result, _ = run(Twice(Broker(ModelAccount.OWN, None)))
    assert [c.model_account for c in result.model_calls] == [
        ModelAccount.OWN,
        ModelAccount.DEPLOYMENT,
    ]


@pytest.mark.parametrize(("status", "reason", "code"), REFUSALS)
def test_a_refused_own_account_ends_the_run_abstained_with_the_calls_made(
    status: int, reason: str, code: ReasonCode
) -> None:
    result, _ = run(Twice(Broker(ModelAccount.OWN, (status, reason))))
    assert result.outcome.status is OutcomeStatus.ABSTAINED
    assert result.outcome.reason_code is code
    # The call the person's account paid for before the refusal is still recorded.
    [made] = result.model_calls
    assert made.model_account is ModelAccount.OWN
    assert set(result.prompts) == {made.prompt_digest}


def test_any_other_provider_error_still_fails_the_run() -> None:
    agent = Twice(Broker(ModelAccount.DEPLOYMENT, (403, "provider-error")))
    with pytest.raises(Exception) as caught:
        run(agent)
    assert refusal(caught.value) is None


def test_a_refusal_is_found_through_the_exceptions_an_agent_wraps_it_in() -> None:
    agent = Twice(Broker((403, "model-account-missing")))
    with pytest.raises(Exception) as caught:
        agent.client.messages.create(model="claude-test", max_tokens=16, messages=[])
    try:
        raise RuntimeError("the model could not be called") from caught.value
    except RuntimeError as wrapped:
        assert refusal(wrapped) is ReasonCode.MODEL_ACCOUNT_MISSING
