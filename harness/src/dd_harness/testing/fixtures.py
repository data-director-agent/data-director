"""The test kit's fixtures: the test profiles, the principal tests act for, and inputs.

The test profiles are in `profiles/`. The inputs are instances of the doubles' own classes
(`classes`), and of the core's `Message`.
"""

from __future__ import annotations

from pathlib import Path

from dd_harness.testing.classes import ProbeClaim, ProbeProfile, ProbeRecord
from dd_sdk.contract.models import Frozen, InvocationRequest, Message, Principal

PROFILES_DIR = Path(__file__).resolve().parent / "profiles"
PERMISSIVE = PROFILES_DIR / "test-permissive.yaml"
RESTRICTIVE = PROFILES_DIR / "test-restrictive.yaml"

# Whom test invocations act for (ADR-0018): the ORCID documentation's example researcher, so a
# stored test run never names a real person.
TEST_PRINCIPAL = Principal(
    principal_id="https://orcid.org/0000-0002-1825-0097", name="Josiah Carberry"
)


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
