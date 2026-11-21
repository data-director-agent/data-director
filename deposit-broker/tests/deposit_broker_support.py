"""Doubles for the deposit broker's tests: a stand-in for the harness that signs deposit grants and
repository enrolment tickets as `dd_harness.deposit_grants` does (the broker does not depend on the
harness), Zenodo's API in memory, and a broker built from them."""

from __future__ import annotations

import base64
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
from joserfc import jwe, jwt
from joserfc.jwk import ECKey, KeySet, RSAKey
from starlette.testclient import TestClient

from dd_deposit_broker.app import DepositBroker, build_app
from dd_deposit_broker.settings import DepositBrokerSettings
from dd_deposit_broker.store import Store
from dd_deposit_broker.tokens import HarnessKeys, Verifier
from dd_deposit_broker.zenodo import OAuthClient
from dd_sdk.deposit_grant import (
    CLAIM_APPROVAL,
    CLAIM_AUDIENCE,
    CLAIM_BASE_URL,
    CLAIM_EXPIRES,
    CLAIM_ISSUED_AT,
    CLAIM_ITEM_DIGEST,
    CLAIM_PACKAGE_DIGEST,
    CLAIM_PURPOSE,
    CLAIM_REPOSITORY,
    CLAIM_SUBJECT,
    CLAIM_TICKET_ID,
    CLAIM_TRANSPORT,
    DEPOSIT_BROKER_AUDIENCE,
    GRANT_TYPE,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
    TICKET_PURPOSE,
    TICKET_TYPE,
    DepositRequest,
    sha256,
)

SANDBOX = "https://sandbox.zenodo.org/api"
PRODUCTION = "https://zenodo.org/api"
PSEUDONYM = "pseud-7c2e4f9a1b3d5e60"
OTHER = "pseud-0a1b2c3d4e5f6789"
PUBLIC_URL = "https://dd.test/deposit-broker"
APP_URL = "https://dd.test"
CLIENT = OAuthClient("dd-test-client", "dd-test-client-secret-0000")
TOKEN = "zenodo-test-token-a1b2c3d4"
ITEM = json.dumps({"metadata": {"title": "Soil cores", "upload_type": "dataset"}}).encode()
PACKAGE = b"PK\x05\x06" + bytes(18)


@dataclass
class FakeHarness:
    """Signs deposit grants and tickets as the harness will, sealing the pseudonym to the broker."""

    signing_key: RSAKey = field(
        default_factory=lambda: RSAKey.generate_key(
            2048, parameters={"kid": "harness-1", "alg": "RS256", "use": "sig"}
        )
    )
    subject_key: ECKey = field(default_factory=lambda: ECKey.generate_key("P-256"))
    serial: int = 0

    def jwks(self) -> dict[str, Any]:
        return dict(KeySet([self.signing_key]).as_dict(private=False))

    def _seal(self, pseudonym: str) -> str:
        public = ECKey.import_key(self.subject_key.as_dict(private=False))
        return jwe.encrypt_compact(
            {"alg": SUBJECT_KEY_ALGORITHM, "enc": SUBJECT_ENCRYPTION},
            pseudonym.encode("utf-8"),
            public,
        )

    def _sign(self, typ: str, claims: Mapping[str, Any], key: RSAKey | None = None) -> str:
        self.serial += 1
        return jwt.encode(
            {"alg": "RS256", "kid": "harness-1", "typ": typ}, dict(claims), key or self.signing_key
        )

    def ticket(self, pseudonym: str = PSEUDONYM, **changes: Any) -> str:
        typ = changes.pop("typ", TICKET_TYPE)
        now = int(time.time())
        claims = {
            CLAIM_AUDIENCE: DEPOSIT_BROKER_AUDIENCE,
            CLAIM_ISSUED_AT: now,
            CLAIM_EXPIRES: now + 120,
            CLAIM_TICKET_ID: f"ticket-{self.serial}",
            CLAIM_PURPOSE: TICKET_PURPOSE,
            CLAIM_SUBJECT: self._seal(pseudonym),
            **changes,
        }
        return self._sign(typ, claims)

    def grant(
        self,
        pseudonym: str = PSEUDONYM,
        *,
        item: bytes = ITEM,
        package: bytes = PACKAGE,
        typ: str = GRANT_TYPE,
        **changes: Any,
    ) -> str:
        now = int(time.time())
        claims = {
            CLAIM_AUDIENCE: DEPOSIT_BROKER_AUDIENCE,
            CLAIM_ISSUED_AT: now,
            CLAIM_EXPIRES: now + 300,
            CLAIM_TICKET_ID: f"grant-{self.serial}",
            CLAIM_SUBJECT: self._seal(pseudonym),
            CLAIM_REPOSITORY: "r3d100010468",
            CLAIM_TRANSPORT: "zenodo",
            CLAIM_BASE_URL: SANDBOX,
            CLAIM_PACKAGE_DIGEST: sha256(package),
            CLAIM_ITEM_DIGEST: sha256(item),
            CLAIM_APPROVAL: "01900000-0000-7000-8000-00000000a001",
            **changes,
        }
        return self._sign(typ, claims)


def body(item: bytes = ITEM, package: bytes = PACKAGE) -> dict[str, str]:
    return DepositRequest(item, package, "ro-crate-abc.zip").to_json()


@dataclass
class FakeZenodo:
    """Zenodo's deposit and OAuth API in memory, at the sandbox. It records every request it is
    sent, and answers as a test sets: `failing` maps a path's last part (`depositions`, the file
    name, `token`) to a status."""

    tokens: dict[str, str] = field(default_factory=lambda: {TOKEN: PSEUDONYM})
    failing: dict[str, int] = field(default_factory=dict)
    requests: list[httpx.Request] = field(default_factory=list)
    drafts: dict[str, dict[str, Any]] = field(default_factory=dict)
    issued: int = 0
    expires_in: int = 3600

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.answer)

    def answer(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        last = path.rsplit("/", 1)[-1]
        if last in self.failing:
            return httpx.Response(self.failing[last], json={"message": f"echo {request.content!r}"})
        if path == "/oauth/token":
            return self._token(request)
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if token not in self.tokens:
            return httpx.Response(401, json={"message": "invalid token"})
        if path == "/api/deposit/depositions" and request.method == "GET":
            return httpx.Response(200, json=[])
        if path == "/api/deposit/depositions" and request.method == "POST":
            number = str(4000 + len(self.drafts))
            self.drafts[number] = {"metadata": json.loads(request.content)["metadata"], "files": {}}
            return httpx.Response(
                201,
                json={
                    "id": int(number),
                    "doi": "",
                    "links": {
                        "bucket": f"https://sandbox.zenodo.org/api/files/bucket-{number}",
                        "html": f"https://sandbox.zenodo.org/deposit/{number}",
                    },
                },
            )
        if path.startswith("/api/files/bucket-") and request.method == "PUT":
            number = path.split("/")[3].removeprefix("bucket-")
            self.drafts[number]["files"][last] = request.content
            return httpx.Response(201, json={"key": last})
        if path.startswith("/api/deposit/depositions/") and request.method == "DELETE":
            self.drafts.pop(last, None)
            return httpx.Response(204)
        return httpx.Response(404)

    def _token(self, request: httpx.Request) -> httpx.Response:
        form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
        if (form.get("client_id"), form.get("client_secret")) != (
            CLIENT.client_id,
            CLIENT.client_secret,
        ):
            return httpx.Response(401, json={"error": "invalid_client"})
        if form.get("grant_type") == "authorization_code" and form.get("code") != "good-code":
            return httpx.Response(400, json={"error": "invalid_grant"})
        if form.get("grant_type") == "refresh_token" and form.get("refresh_token") not in {
            f"refresh-{n}" for n in range(1, self.issued + 1)
        }:
            return httpx.Response(400, json={"error": "invalid_grant"})
        self.issued += 1
        access = f"oauth-access-{self.issued}-xyz"
        self.tokens[access] = PSEUDONYM
        return httpx.Response(
            200,
            json={
                "access_token": access,
                "refresh_token": f"refresh-{self.issued}",
                "expires_in": self.expires_in,
                "token_type": "Bearer",
                "scope": "deposit:write",
            },
        )


def kek_b64() -> str:
    return base64.b64encode(os.urandom(32)).decode("ascii")


@dataclass
class Running:
    broker: DepositBroker
    client: TestClient
    harness: FakeHarness
    zenodo: FakeZenodo


def make_broker(
    tmp_path: Path,
    *,
    harness: FakeHarness | None = None,
    zenodo: FakeZenodo | None = None,
    allowed: Mapping[str, str] | None = None,
    oauth: bool = True,
) -> Running:
    harness = harness or FakeHarness()
    zenodo = zenodo or FakeZenodo()
    settings = DepositBrokerSettings(
        key_encryption_key=os.urandom(32),
        subject_key=harness.subject_key,
        store=tmp_path / "deposit-broker.sqlite",
        allowed=dict(allowed or {SANDBOX: "zenodo"}),
        oauth_clients={SANDBOX: CLIENT} if oauth else {},
        harness_jwks_file=tmp_path / "jwks.json",
        public_url=PUBLIC_URL,
        app_url=APP_URL,
    )
    store = Store(settings.store, settings.key_encryption_key)
    verifier = Verifier(HarnessKeys(harness.jwks), settings.subject_key, store)
    broker = DepositBroker(settings, store, verifier, zenodo.transport())
    client = TestClient(build_app(broker), base_url="https://dd.test")
    return Running(broker, client, harness, zenodo)
