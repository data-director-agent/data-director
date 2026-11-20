"""The deposit broker makes a draft for a harness that presents a deposit grant, with the token of
the person the grant names, and never publishes (docs/specs/deposit.md, invariants 12 to 15)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from deposit_broker_support import (
    ITEM,
    PACKAGE,
    PRODUCTION,
    PSEUDONYM,
    SANDBOX,
    TOKEN,
    FakeZenodo,
    Running,
    body,
    make_broker,
)

from dd_deposit_broker.store import OAUTH, Tokens
from dd_deposit_broker.store import TOKEN as BY_TOKEN
from dd_sdk.deposit_grant import (
    CLAIM_AUDIENCE,
    CLAIM_EXPIRES,
    CLAIM_ISSUED_AT,
    DEPOSITS_PATH,
    HEADER_GRANT,
    HEADER_REASON,
)


@pytest.fixture
def running(tmp_path: Path) -> Running:
    running = make_broker(tmp_path)
    running.broker.store.put(PSEUDONYM, SANDBOX, Tokens(TOKEN), method=BY_TOKEN, label="token")
    return running


def post(running: Running, grant: str | None, payload: dict[str, str] | None = None):  # type: ignore[no-untyped-def]
    headers = {HEADER_GRANT: grant} if grant else {}
    return running.client.post(DEPOSITS_PATH, json=payload or body(), headers=headers)


def test_a_grant_makes_a_draft_with_the_item_and_the_package(running: Running) -> None:
    answer = post(running, running.harness.grant())
    assert answer.status_code == 201
    assert answer.json() == {
        "deposit_id": "4000",
        "draft_url": "https://sandbox.zenodo.org/deposit/4000",
    }
    (draft,) = running.zenodo.drafts.values()
    assert draft["metadata"] == json.loads(ITEM)["metadata"]
    assert draft["files"] == {"ro-crate-abc.zip": PACKAGE}
    assert answer.headers["cache-control"] == "no-store"


def test_nothing_the_broker_sends_publishes(running: Running) -> None:
    """Invariant 14: no request names the publish action, and every one uses the person's token."""
    post(running, running.harness.grant())
    assert running.zenodo.requests
    for request in running.zenodo.requests:
        assert "publish" not in str(request.url)
        assert "/actions/" not in str(request.url)
        assert request.headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.parametrize(
    ("grant_changes", "status", "reason"),
    [
        ({CLAIM_AUDIENCE: "urn:data-director:model-broker"}, 401, "grant-invalid"),
        ({"typ": "JWT"}, 401, "grant-invalid"),
        ({CLAIM_ISSUED_AT: 1, CLAIM_EXPIRES: 2}, 401, "grant-expired"),
        ({"dd_base_url": PRODUCTION}, 400, "base-url-not-allowed"),
        ({"dd_transport": "figshare"}, 400, "transport-unknown"),
        ({"dd_package_digest": "0" * 64}, 400, "digest-mismatch"),
    ],
)
def test_a_grant_that_does_not_hold_is_refused_before_any_call(
    running: Running, grant_changes: dict[str, Any], status: int, reason: str
) -> None:
    answer = post(running, running.harness.grant(**grant_changes))
    assert (answer.status_code, answer.headers[HEADER_REASON]) == (status, reason)
    assert running.zenodo.requests == []


def test_a_missing_grant_is_refused(running: Running) -> None:
    answer = post(running, None)
    assert (answer.status_code, answer.headers[HEADER_REASON]) == (401, "grant-missing")


def test_a_grant_is_accepted_once(running: Running) -> None:
    grant = running.harness.grant()
    assert post(running, grant).status_code == 201
    again = post(running, grant)
    assert (again.status_code, again.headers[HEADER_REASON]) == (401, "grant-used")
    assert len(running.zenodo.drafts) == 1


def test_a_body_other_than_the_one_granted_is_refused(running: Running) -> None:
    answer = post(running, running.harness.grant(), body(package=b"other"))
    assert (answer.status_code, answer.headers[HEADER_REASON]) == (400, "digest-mismatch")


def test_a_person_without_an_account_is_told_so(running: Running) -> None:
    answer = post(running, running.harness.grant("pseud-nobody"))
    assert (answer.status_code, answer.headers[HEADER_REASON]) == (403, "account-missing")
    assert running.zenodo.requests == []


@pytest.mark.parametrize(
    ("failing", "status", "reason"),
    [
        ({"depositions": 401}, 403, "account-rejected"),
        ({"depositions": 400}, 400, "item-rejected"),
        ({"depositions": 503}, 502, "repository-unavailable"),
    ],
)
def test_a_repository_failure_is_a_reason_code_never_its_message(
    tmp_path: Path, failing: dict[str, int], status: int, reason: str
) -> None:
    running = make_broker(tmp_path, zenodo=FakeZenodo(failing=failing))
    running.broker.store.put(PSEUDONYM, SANDBOX, Tokens(TOKEN), method=BY_TOKEN, label="token")
    answer = post(running, running.harness.grant())
    assert (answer.status_code, answer.headers[HEADER_REASON]) == (status, reason)
    assert answer.content == b""


def test_a_failed_upload_leaves_no_draft_behind(tmp_path: Path) -> None:
    running = make_broker(tmp_path, zenodo=FakeZenodo(failing={"ro-crate-abc.zip": 500}))
    running.broker.store.put(PSEUDONYM, SANDBOX, Tokens(TOKEN), method=BY_TOKEN, label="token")
    answer = post(running, running.harness.grant())
    assert answer.headers[HEADER_REASON] == "repository-unavailable"
    assert running.zenodo.drafts == {}
    assert running.zenodo.requests[-1].method == "DELETE"


def test_an_expiring_oauth_token_is_refreshed_and_kept(tmp_path: Path) -> None:
    running = make_broker(tmp_path)
    zenodo = running.zenodo
    zenodo.issued = 1
    zenodo.tokens["oauth-access-1-xyz"] = PSEUDONYM
    stale = Tokens("oauth-access-1-xyz", "refresh-1", int(time.time()) - 10)
    running.broker.store.put(PSEUDONYM, SANDBOX, stale, method=OAUTH, label="signed in")
    assert post(running, running.harness.grant()).status_code == 201
    kept = running.broker.store.account(PSEUDONYM, SANDBOX)
    assert kept is not None
    assert kept.tokens.access_token == "oauth-access-2-xyz"
    assert zenodo.requests[-1].headers["authorization"] == "Bearer oauth-access-2-xyz"
