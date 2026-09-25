"""hello.world: the template agent. Greets whoever the input names, and nothing else.

This package exists to be copied. It is the smallest agent that walks the whole recipe in
`agents/README.md` — a new input class, a new payload class, a grounding mode, the payload's
derivations, a console script, a profile entry, a sample and marked tests — with no domain logic
in the way. It runs as its own service (`dd-hello serve`); the workbench reaches it over A2A.
`quality.reviewer` and `fact.checker` show what a real agent does; this one shows only what the
harness requires. Read it top to bottom, then delete the greeting.

It also keeps the workbench's modularity claim honest: if adding an agent ever starts to require
an edit to the conductor, linter, CLI, transport or viewer, this agent will be the one that shows
it, because it has no other reason to fail.

Grounding mode `none` (ADR-0008): deterministic over the input, no retrieval and no model call.
The linter applies R1 (no retrieval span), R2 (everything cites the input), R3 (a succeeded run
cites the input) and N1 (no chat span). The single legal citation is the input itself, whose
source id and content hash the conductor computed and handed over in `ctx`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from dd_sdk import serve
from dd_sdk.agent import AgentResult, AgentSpec, Derived, RunContext
from dd_sdk.contract.models import (
    Derivation,
    EvidenceItem,
    Greeting,
    GroundingMode,
    GroundingRef,
    InvocationRequest,
    Outcome,
    OutcomeStatus,
    ReasonCode,
    Salutation,
)
from dd_sdk.evidence import HASH_ALGORITHM, INPUT_CANONICALISATION

# The whole of this agent's domain knowledge. A real agent would load a rule file or reach a
# backend here; the point is that neither is the harness's business.
GREETINGS = {"en": "Hello", "cy": "Helo", "fr": "Bonjour", "de": "Hallo"}
DEFAULT_LANGUAGE = "en"


class HelloWorld:
    # Step 4: an agent is this attribute plus `run`. The conductor holds it to every field —
    # it refuses an input class not in `accepts`, refuses a payload that is not `payload_type`,
    # writes `grounding_mode` onto the envelope itself, and matches `action_class` against the
    # institutional profile's `actions_requiring_approval`.
    spec = AgentSpec(
        agent_id="hello.world",
        version="0.1.0",
        description=(
            "Greets whoever the input names. A template: it demonstrates the agent contract and "
            "does nothing useful."
        ),
        action_class="advise",
        accepts=(Salutation,),
        grounding_mode=GroundingMode.NONE,
        payload_type=Greeting,
        # Step 8 of the recipe: how each field that is not copied from the input comes about. The
        # viewer badges `greeting_text` from this, reading `greeting_derivation` per value.
        derivations={
            "greeting_text": Derived(Derivation.TEMPLATE, recorded_in="greeting_derivation")
        },
    )

    def run(self, request: InvocationRequest, ctx: RunContext) -> AgentResult:
        salutation = request.input
        # Not defensive: the conductor already refused anything outside `spec.accepts` with
        # `failed(input-not-accepted)`. The assertion is for the type checker and the reader.
        assert isinstance(salutation, Salutation)

        language = (salutation.language or DEFAULT_LANGUAGE).split("-")[0].lower()
        if language not in GREETINGS:
            # A content problem is an outcome, not an exception. Exceptions are reserved for
            # programmer and configuration errors.
            return AgentResult(
                outcome=Outcome(
                    status=OutcomeStatus.ABSTAINED,
                    reason_code=ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
                    statement=(
                        f"No greeting is packaged for language {language!r}; "
                        f"this agent knows {', '.join(sorted(GREETINGS))}."
                    ),
                )
            )

        # The one identity this payload rests on. Under `none` and `input_only` it is always the
        # input and only the input; `ctx.input_ref` and `ctx.input_hash` come from the conductor,
        # so an agent cannot misreport what it worked from.
        ref = GroundingRef(source_id=ctx.input_ref, content_hash=ctx.input_hash)

        return AgentResult(
            outcome=Outcome(
                status=OutcomeStatus.SUCCEEDED,
                statement="Greeted the name given. Deterministic; human review is required.",
            ),
            # `Greeting` mixes in `Grounded`, so `grounded_on` is part of the payload. A payload
            # without it fails the linter (G0) rather than passing unnoticed.
            payload=Greeting(
                greeting_text=f"{GREETINGS[language]}, {salutation.greeted_name}!",
                # The badge the viewer renders beside `greeting_text`: filled from a format
                # string, not written by a model.
                greeting_derivation=Derivation.TEMPLATE,
                grounded_on=[ref],
            ),
            # Step 3: the canonicalisation is a registered name from `dd_sdk.evidence` (ADR-0009),
            # never a literal invented here.
            evidence=[
                EvidenceItem(
                    source_id=ctx.input_ref,
                    retrieved_at=datetime.now(UTC),
                    hash_algorithm=HASH_ALGORITHM,
                    canonicalisation=INPUT_CANONICALISATION,
                    content_hash=ctx.input_hash,
                )
            ],
            # `model_id` and the token counts stay unset: mode `none` calls no model. The
            # conductor fills the rest of the telemetry, and every identifier and timestamp.
        )


def build() -> HelloWorld:
    """The factory `main` serves (step 4). An agent that needed configuration would read its own
    `DD_HELLO_*` environment variables here: the workbench's settings are not the agent's."""
    return HelloWorld()


def main() -> int:
    """The `dd-hello` console script (step 4): serve this agent over A2A with `dd_sdk.serve`."""
    return serve.main(build)
