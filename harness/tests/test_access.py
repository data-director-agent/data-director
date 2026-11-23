"""Whom a deployment admits: the profile's `access` key (docs/specs/policy-and-identity.md,
Admission; #292).

A deployment admits anyone the provider vouches for, or only the people it lists and its
stewards and administrators; a blocked person is refused whatever else lists them. The way in
checks this at sign-in and on every request, so a person blocked after signing in loses their
session at their next request.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from dd_harness.access import Access, Admission
from dd_harness.policy import PolicyError, Profile
from dd_harness.sessions import SESSION_COOKIE, NotAdmitted, SessionAuthenticator, SessionStore
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL
from dd_sdk.contract.models import Principal

ADA = "https://orcid.org/0000-0001-5000-0007"
JOSIAH = "https://orcid.org/0000-0002-1825-0097"
GRACE = "https://orcid.org/0000-0002-1694-233X"
ISSUER = "https://orcid.org"

TEAM = {"id": "library-rdm", "name": "Library Research Data Team", "members": [GRACE]}


def profile(**keys: Any) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data.update(keys)
    return Profile.from_mapping(data, source="test", digest="0" * 64)


def person(principal_id: str, vouched_by: str | None = ISSUER) -> Principal:
    return TEST_PRINCIPAL.model_copy(
        update={
            "principal_id": principal_id,
            "assurance": "authenticated",
            "vouched_by": vouched_by,
        }
    )


def test_a_profile_without_access_admits_anyone() -> None:
    found = profile()
    assert found.access == Access()
    assert all(found.admits(p) for p in (ADA, JOSIAH, GRACE))


def test_an_open_profile_still_refuses_whom_it_blocks() -> None:
    found = profile(access={"block": [ADA]})
    assert not found.admits(ADA)
    assert found.admits(JOSIAH)


def test_a_closed_profile_admits_whom_it_lists_and_its_stewards_and_administrators() -> None:
    found = profile(
        access={"admit": "listed", "allow": [ADA]},
        administrators=[JOSIAH],
        stewardship={"teams": [TEAM]},
    )
    assert found.admits(ADA)
    assert found.admits(JOSIAH)
    assert found.admits(GRACE)
    assert not found.admits("https://orcid.org/0000-0003-1415-9269")


def test_a_closed_profile_with_no_list_admits_only_its_roles() -> None:
    found = profile(access={"admit": "listed"}, administrators=[JOSIAH])
    assert found.admits(JOSIAH)
    assert not found.admits(ADA)


def test_blocking_refuses_an_administrator_and_a_steward_too() -> None:
    found = profile(
        access={"admit": "listed", "block": [JOSIAH, GRACE]},
        administrators=[JOSIAH],
        stewardship={"teams": [TEAM]},
    )
    assert not found.admits(JOSIAH)
    assert not found.admits(GRACE)


@pytest.mark.parametrize(
    "access",
    [
        ["listed"],
        {"admit": "nobody"},
        {"admit": "listed", "deny": [ADA]},
        {"allow": [ADA]},
        {"admit": "listed", "allow": [ADA], "block": [ADA]},
        {"block": ["0000-0001-5000-0007"]},
        {"block": [""]},
    ],
)
def test_an_access_key_that_cannot_be_enforced_as_written_is_refused(access: Any) -> None:
    with pytest.raises(PolicyError):
        profile(access=access)


def test_admission_is_on_the_issuer_and_the_identifier_only() -> None:
    admission = Admission(ISSUER, profile(access={"admit": "listed", "allow": [ADA]}).admits)
    assert admission(person(ADA))
    assert not admission(person(ADA, vouched_by="https://elsewhere.example"))
    assert not admission(person(ADA, vouched_by=None))
    assert not admission(person(JOSIAH))
    renamed = person(ADA).model_copy(update={"name": "Someone else"})
    assert admission(renamed)


def test_a_session_of_someone_no_longer_admitted_is_ended_at_their_next_request() -> None:
    admitted = {ADA}
    store = SessionStore()
    authenticator = SessionAuthenticator(
        store, SESSION_COOKIE, lambda p: p.principal_id in admitted
    )
    session_id = store.create(person(ADA))
    headers = {"cookie": f"{SESSION_COOKIE}={session_id}"}
    assert authenticator.principal_for(headers).principal_id == ADA

    admitted.clear()
    with pytest.raises(NotAdmitted) as refused:
        authenticator.principal_for(headers)
    assert refused.value.principal.principal_id == ADA
    assert store.get(session_id) is None
    # Admitted again, the ended session stays ended: the person signs in afresh.
    admitted.add(ADA)
    assert authenticator.session(headers) is None
