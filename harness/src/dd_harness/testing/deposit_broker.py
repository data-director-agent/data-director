"""The deposit broker in memory, for tests of depositing through an API (docs/specs/deposit.md).

`FakeDepositBroker` answers `POST /deposits` as the real broker does, over `httpx.MockTransport`:
it checks the grant's signature against the harness's published keys, opens the sealed pseudonym
with its own subject key, and checks that the body's bytes are the ones the grant names. It then
makes a draft, or answers with the status and reason a test sets in `failing`. It keeps what it
was sent, so a test can show that nothing carried a token and nothing asked to publish.

`deposit_broker()` gives the harness's `DepositBroker` wired to it. No key here is used outside a
test.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
from joserfc.jwk import ECKey

from dd_harness.deposit_broker import DepositBroker
from dd_harness.deposit_grants import DepositGrantMinter
from dd_harness.testing.model_grants import GrantKeys
from dd_sdk.deposit_grant import (
    DEPOSIT_BROKER_AUDIENCE,
    DEPOSITS_PATH,
    GRANT_TYPE,
    HEADER_GRANT,
    HEADER_REASON,
    DepositAnswer,
    DepositGrantClaims,
    DepositReason,
    DepositRequest,
    sha256,
)

BROKER_URL = "http://127.0.0.1:8310"


@dataclass(frozen=True)
class Received:
    """One request the fake accepted: the grant's claims, the person's pseudonym, the body."""

    claims: DepositGrantClaims
    pseudonym: str
    request: DepositRequest
    headers: dict[str, str]


@dataclass
class FakeDepositBroker:
    keys: GrantKeys = field(default_factory=GrantKeys)
    subject_key: ECKey = field(default_factory=lambda: ECKey.generate_key("P-256"))
    # A status and reason to answer every request with, instead of making a draft.
    failing: tuple[int, DepositReason] | None = None
    # The pseudonyms that have connected an account; None means everyone has.
    accounts: set[str] | None = None
    received: list[Received] = field(default_factory=list)
    _used: set[str] = field(default_factory=set)

    def minter(self) -> DepositGrantMinter:
        public = ECKey.import_key(self.subject_key.as_dict(private=False))
        return DepositGrantMinter(self.keys.minter(), public)

    def deposit_broker(self) -> DepositBroker:
        return DepositBroker(BROKER_URL, self.minter(), httpx.MockTransport(self.answer))

    def answer(self, request: httpx.Request) -> httpx.Response:
        if request.method != "POST" or request.url.path != DEPOSITS_PATH:
            return httpx.Response(404)
        opened = self._open(request)
        if isinstance(opened, httpx.Response):
            return opened
        claims, pseudonym = opened
        body = DepositRequest.from_json(json.loads(request.content))
        if sha256(body.package) != claims.package_digest or sha256(body.item) != (
            claims.item_digest
        ):
            return _refused(400, DepositReason.DIGEST_MISMATCH)
        self.received.append(Received(claims, pseudonym, body, dict(request.headers)))
        if self.failing is not None:
            return _refused(*self.failing)
        if self.accounts is not None and pseudonym not in self.accounts:
            return _refused(403, DepositReason.ACCOUNT_MISSING)
        number = str(1000 + len(self.received))
        answer = DepositAnswer(number, f"https://sandbox.zenodo.org/deposit/{number}")
        return httpx.Response(201, json=answer.to_json())

    def _open(self, request: httpx.Request) -> tuple[DepositGrantClaims, str] | httpx.Response:
        """The grant's claims and the person's pseudonym, or the refusal to answer with."""
        token = request.headers.get(HEADER_GRANT)
        if not token:
            return _refused(401, DepositReason.GRANT_MISSING)
        opened = GrantKeys(self.keys.signing_key, self.subject_key, self.keys.secret).open(token)
        if opened.header.get("typ") != GRANT_TYPE:
            return _refused(401, DepositReason.GRANT_INVALID)
        claims = DepositGrantClaims.from_claims(opened.claims)
        if claims.audience != DEPOSIT_BROKER_AUDIENCE:
            return _refused(401, DepositReason.GRANT_INVALID)
        if claims.grant_id in self._used:
            return _refused(401, DepositReason.GRANT_USED)
        self._used.add(claims.grant_id)
        return claims, opened.pseudonym

    def item(self, n: int = -1) -> dict[str, Any]:
        """The item the `n`th accepted request carried, as JSON."""
        loaded: dict[str, Any] = json.loads(self.received[n].request.item)
        return loaded


def _refused(status: int, reason: DepositReason) -> httpx.Response:
    return httpx.Response(status, headers={HEADER_REASON: reason.value})
