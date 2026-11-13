"""Doubles for the broker's tests: a stand-in for the harness that signs model grants as
`dd_harness.model_grants` does (the broker does not depend on the harness), agent credentials, and
a broker built from them."""

from __future__ import annotations

import base64
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
from joserfc import jwe, jwt
from joserfc.jwk import ECKey, KeySet, RSAKey
from starlette.testclient import TestClient

from dd_broker.agents import AgentCredentials, digest
from dd_broker.app import Broker, build_app
from dd_broker.grants import GrantVerifier, HarnessKeys, TicketVerifier
from dd_broker.store import Store
from dd_sdk.model_grant import (
    BROKER_AUDIENCE,
    HEADER_GRANT,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
    TICKET_PURPOSE,
    TICKET_TYPE,
    Account,
)

AGENT = "advisor.standards"
AGENT_CREDENTIAL = "dd-broker-test-credential-advisor-standards-5c1f"
OTHER_AGENT = "advisor.policy"
OTHER_CREDENTIAL = "dd-broker-test-credential-advisor-policy-a94e"
MODEL = "claude-sonnet-5-5"
PSEUDONYM = "pseud-3f9a1c7e0b2d4a68"
DEPLOYMENT_KEY = "sk-ant-deployment-test-0000"
GATEWAY = "http://gateway.test:4000"


def key_encryption_key() -> bytes:
    return os.urandom(32)


def key_encryption_key_b64() -> str:
    return base64.b64encode(key_encryption_key()).decode("ascii")


@dataclass
class FakeHarness:
    """Signs model grants as the harness will, and seals the pseudonym to the broker."""

    signing_key: RSAKey = field(
        default_factory=lambda: RSAKey.generate_key(
            2048, parameters={"kid": "harness-1", "alg": "RS256", "use": "sig"}
        )
    )
    subject_key: ECKey = field(default_factory=lambda: ECKey.generate_key("P-256"))
    fetches: int = 0

    def jwks(self) -> dict[str, Any]:
        self.fetches += 1
        return dict(KeySet([self.signing_key]).as_dict(private=False))

    def keys(self, clock: Callable[[], float] = time.monotonic) -> HarnessKeys:
        return HarnessKeys(self.jwks, clock=clock)

    def seal_subject(self, pseudonym: str = PSEUDONYM) -> str:
        public = ECKey.import_key(self.subject_key.as_dict(private=False))
        return jwe.encrypt_compact(
            {"alg": SUBJECT_KEY_ALGORITHM, "enc": SUBJECT_ENCRYPTION},
            pseudonym.encode("utf-8"),
            public,
        )

    def claims(
        self,
        *,
        agent: str = AGENT,
        account: Account = Account.OWN,
        models: Sequence[str] = (MODEL,),
        pseudonym: str = PSEUDONYM,
        lifetime: int = 300,
        issued_at: int | None = None,
    ) -> dict[str, Any]:
        now = int(time.time()) if issued_at is None else issued_at
        return {
            "aud": BROKER_AUDIENCE,
            "iat": now,
            "exp": now + lifetime,
            "dd_agent": agent,
            "dd_invocation": "inv-0001",
            "dd_models": list(models),
            "dd_account": account.value,
            "dd_subject": self.seal_subject(pseudonym),
        }

    def sign(self, claims: dict[str, Any], key: RSAKey | None = None) -> str:
        key = key or self.signing_key
        return jwt.encode({"alg": "RS256", "kid": key.kid}, claims, key)

    def grant(self, **kwargs: Any) -> str:
        return self.sign(self.claims(**kwargs))

    def verifier(self) -> GrantVerifier:
        return GrantVerifier(self.keys(), self.subject_key)

    def ticket_claims(
        self,
        *,
        pseudonym: str = PSEUDONYM,
        lifetime: int = 120,
        issued_at: int | None = None,
        jti: str | None = None,
    ) -> dict[str, Any]:
        now = int(time.time()) if issued_at is None else issued_at
        return {
            "aud": BROKER_AUDIENCE,
            "iat": now,
            "exp": now + lifetime,
            "jti": jti or os.urandom(12).hex(),
            "dd_purpose": TICKET_PURPOSE,
            "dd_subject": self.seal_subject(pseudonym),
        }

    def ticket(self, typ: str = TICKET_TYPE, **kwargs: Any) -> str:
        """An enrolment ticket as `GrantMinter.enrolment_ticket` signs one."""
        key = self.signing_key
        return jwt.encode(
            {"alg": "RS256", "kid": key.kid, "typ": typ}, self.ticket_claims(**kwargs), key
        )

    def tickets(self, store: Store) -> TicketVerifier:
        return TicketVerifier(self.keys(), self.subject_key, store)


def agents() -> AgentCredentials:
    return AgentCredentials(
        {AGENT: digest(AGENT_CREDENTIAL), OTHER_AGENT: digest(OTHER_CREDENTIAL)}
    )


def public_resolver(host: str, port: int) -> list[str]:
    return ["93.184.215.14"]


def make_broker(
    harness: FakeHarness,
    store_path: Path,
    *,
    deployment_key: str | None = DEPLOYMENT_KEY,
    deployment_base_url: str | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    kek: bytes | None = None,
    allowed: Sequence[str] = (),
) -> Broker:
    store = Store(store_path, kek or key_encryption_key())
    return Broker(
        store=store,
        verifier=harness.verifier(),
        tickets=harness.tickets(store),
        agents=agents(),
        deployment_key=deployment_key,
        deployment_base_url=deployment_base_url,
        allowed_base_urls=allowed,
        resolve=public_resolver,
        transport=transport,
    )


def client(broker: Broker) -> TestClient:
    return TestClient(build_app(broker), raise_server_exceptions=True)


def message_body(model: str = MODEL, **extra: Any) -> dict[str, Any]:
    return {
        "model": model,
        "max_tokens": 64,
        "messages": [{"role": "user", "content": "Which standard fits?"}],
        **extra,
    }


def call_headers(grant: str | None, credential: str = AGENT_CREDENTIAL) -> dict[str, str]:
    headers = {"x-api-key": credential, "anthropic-version": "2023-06-01"}
    if grant is not None:
        headers[HEADER_GRANT] = grant
    return headers


def broker_calls_only(request: Any) -> Any:
    """vcrpy's `before_record_request`: the test client's own requests to the app in memory are
    not provider calls, so they pass by the cassette."""
    return None if request.host == "testserver" else request
