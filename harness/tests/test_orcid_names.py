"""People's names from their public ORCID records, for a page to show (docs/specs/projects.md,
Roles; `dd_harness.orcid.fetch_public_name`, `dd_harness.orcid_names`)."""

from __future__ import annotations

import threading

import httpx
import pytest

from dd_harness import orcid
from dd_harness.orcid_names import KEPT_S, MISSED_S, PublicNames
from dd_harness.testing import SAMPLE_ID, FakeOrcidRegistry, sample_record

PRINCIPAL = f"https://sandbox.orcid.org/{SAMPLE_ID}"
OTHER_ID = "0000-0001-5109-3700"


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_the_name_is_read_from_the_person_section() -> None:
    registry = FakeOrcidRegistry()
    assert orcid.name_url(PRINCIPAL) == f"https://pub.sandbox.orcid.org/v3.0/{SAMPLE_ID}/person"
    name = orcid.fetch_public_name(PRINCIPAL, transport=registry.transport())
    assert name == "Josiah Carberry"


def test_the_credit_name_comes_first() -> None:
    record = sample_record()
    record["person"]["name"]["credit-name"] = {"value": "J. S. Carberry"}
    registry = FakeOrcidRegistry(records={SAMPLE_ID: record})
    assert orcid.fetch_public_name(PRINCIPAL, transport=registry.transport()) == "J. S. Carberry"


def test_a_private_or_unknown_name_is_none() -> None:
    record = sample_record()
    record["person"]["name"] = None
    registry = FakeOrcidRegistry(records={SAMPLE_ID: record})
    assert orcid.fetch_public_name(PRINCIPAL, transport=registry.transport()) is None
    unknown = f"https://sandbox.orcid.org/{OTHER_ID}"
    assert orcid.fetch_public_name(unknown, transport=registry.transport()) is None


@pytest.mark.parametrize(
    "principal",
    [
        f"https://sandbox.orcid.org/{SAMPLE_ID}/record",
        "https://accounts.example.org/someone",
        SAMPLE_ID,
    ],
)
def test_a_principal_that_is_not_an_orcid_id_has_no_name(principal: str) -> None:
    registry = FakeOrcidRegistry()
    assert orcid.name_url(principal) is None
    assert orcid.fetch_public_name(principal, transport=registry.transport()) is None
    assert registry.requests == 0


def test_an_orcid_that_fails_is_unavailable() -> None:
    registry = FakeOrcidRegistry(failing=503)
    with pytest.raises(orcid.OrcidUnavailableError):
        orcid.fetch_public_name(PRINCIPAL, transport=registry.transport())


def test_a_name_is_held_for_a_while() -> None:
    registry = FakeOrcidRegistry()
    clock = Clock()
    names = PublicNames(transport=registry.transport(), clock=clock)
    assert names.names([PRINCIPAL, PRINCIPAL]) == {PRINCIPAL: "Josiah Carberry"}
    assert names.names([PRINCIPAL]) == {PRINCIPAL: "Josiah Carberry"}
    assert registry.requests == 1
    clock.now += KEPT_S
    names.names([PRINCIPAL])
    assert registry.requests == 2


def test_a_name_that_could_not_be_read_is_asked_for_again_later() -> None:
    registry = FakeOrcidRegistry(failing=503)
    clock = Clock()
    names = PublicNames(transport=registry.transport(), clock=clock)
    assert names.names([PRINCIPAL]) == {}
    assert names.names([PRINCIPAL]) == {}
    assert registry.requests == 1
    registry.failing = None
    clock.now += MISSED_S
    assert names.names([PRINCIPAL]) == {PRINCIPAL: "Josiah Carberry"}


def test_a_page_does_not_wait_for_a_slow_orcid() -> None:
    release = threading.Event()
    fast = FakeOrcidRegistry().transport()

    def answer(request: httpx.Request) -> httpx.Response:
        if OTHER_ID in str(request.url):
            release.wait(5)
            return httpx.Response(404)
        return fast.handle_request(request)

    names = PublicNames(transport=httpx.MockTransport(answer), deadline_s=0.2)
    slow = f"https://sandbox.orcid.org/{OTHER_ID}"
    try:
        assert names.names([PRINCIPAL, slow]) == {PRINCIPAL: "Josiah Carberry"}
    finally:
        release.set()
