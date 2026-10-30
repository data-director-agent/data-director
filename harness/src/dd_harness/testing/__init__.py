"""The harness's test kit: scripted doubles and a conductor over them, for the harness's own
tests, for agent packages, and for any way in to the harness (the workbench, the app).

Import everything from here; the modules are an internal arrangement:

- `serving`: `in_process` and `make_conductor`, which serve agents and the conductor in memory
  over the real A2A wire, and `send_to_harness`.
- `doubles`: `AbstainingStub`, `DocumentStub` and `ScriptedAgent`, with the spans a scripted
  agent emits.
- `results`: results a scripted agent can return, and the sources they are grounded on.
- `classes`: the doubles' own `Probe*` classes, declared in `../schema/doubles.yaml`.
- `fixtures`: the test profiles (in `profiles/`), `TEST_PRINCIPAL` and inputs.
- `identity`: `FakeIdentityProvider`, an OpenID Connect provider in memory (ADR-0029).

Nothing here needs the workbench (ADR-0022) or knows about any real agent.
"""

from dd_harness.testing.classes import (
    ProbeCheck,
    ProbeClaim,
    ProbeDocumentRequest,
    ProbeProfile,
    ProbeRecord,
    ProbeReview,
)
from dd_harness.testing.doubles import (
    SPECS,
    AbstainingStub,
    Behaviour,
    Chat,
    DocumentStub,
    Retrieve,
    ScriptedAgent,
)
from dd_harness.testing.fixtures import (
    PERMISSIVE,
    PROFILES_DIR,
    RESTRICTIVE,
    TEST_PRINCIPAL,
    claim,
    document_request,
    message,
    profile,
    record,
    request,
)
from dd_harness.testing.identity import FakeIdentityProvider
from dd_harness.testing.results import (
    SOURCE_A,
    SOURCE_B,
    fact_check_over,
    grant_token,
    input_evidence,
    input_ref,
    reply_over,
    review_of_input,
)
from dd_harness.testing.serving import (
    HARNESS_URL,
    asgi_client_factory,
    in_process,
    make_conductor,
    send_to_harness,
)

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
    "DocumentStub",
    "FakeIdentityProvider",
    "ProbeCheck",
    "ProbeClaim",
    "ProbeDocumentRequest",
    "ProbeProfile",
    "ProbeRecord",
    "ProbeReview",
    "Retrieve",
    "ScriptedAgent",
    "asgi_client_factory",
    "claim",
    "document_request",
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
    "send_to_harness",
]
