"""The deposit grant's format, and the wire between the harness and the deposit broker
(docs/specs/deposit.md, Depositing through an API).

A researcher's repository token is held by the deposit broker, a service outside the app and the
harness, as a person's own model key is held by the model broker. The harness never sees the
token. When a person approves a deposit, the harness signs a **deposit grant**: a JWT that lets the
deposit broker create one draft, in one repository, with exactly the bytes the person approved, as
that person. The broker verifies it and makes the repository's API calls itself.

This module holds only what the harness and the deposit broker must agree on: the audience, the
JOSE types, the claim names, the HTTP headers, the request and answer bodies and the reason codes.
Minting is the harness's (`dd_harness.deposit_grants`). Verifying is the deposit broker's own code,
because checking a grant is governance.

The signing algorithms and the sealing of the person's pseudonym are the model grant's
(`dd_sdk.model_grant`), so one harness key signs both. The audience and the `typ` differ, so a
deposit grant never passes as a model grant, nor a model grant as a deposit grant, and each broker
accepts only its own.

The **repository enrolment ticket** is the grant's sibling, as the model broker's enrolment ticket
is: a single-use token the browser presents to the deposit broker when the signed-in person
connects, reads or disconnects a repository account. It names the person by their sealed pseudonym
and nothing else.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from dd_sdk.contract.base import REPOSITORY_ID_PATTERN
from dd_sdk.model_grant import (
    CLAIM_AUDIENCE,
    CLAIM_EXPIRES,
    CLAIM_ISSUED_AT,
    CLAIM_PURPOSE,
    CLAIM_SUBJECT,
    CLAIM_TICKET_ID,
    SIGNING_ALGORITHMS,
    SUBJECT_ENCRYPTION,
    SUBJECT_KEY_ALGORITHM,
)

__all__ = [
    "CLAIM_APPROVAL",
    "CLAIM_AUDIENCE",
    "CLAIM_BASE_URL",
    "CLAIM_EXPIRES",
    "CLAIM_ISSUED_AT",
    "CLAIM_ITEM_DIGEST",
    "CLAIM_PACKAGE_DIGEST",
    "CLAIM_PURPOSE",
    "CLAIM_REPOSITORY",
    "CLAIM_SUBJECT",
    "CLAIM_TARGET",
    "CLAIM_TICKET_ID",
    "CLAIM_TRANSPORT",
    "DEPOSITS_PATH",
    "DEPOSIT_BROKER_AUDIENCE",
    "GRANT_LIFETIME_S",
    "GRANT_TYPE",
    "HEADER_GRANT",
    "HEADER_REASON",
    "SIGNING_ALGORITHMS",
    "SUBJECT_ENCRYPTION",
    "SUBJECT_KEY_ALGORITHM",
    "TICKET_LIFETIME_S",
    "TICKET_PURPOSE",
    "TICKET_TYPE",
    "DepositAnswer",
    "DepositGrantClaims",
    "DepositGrantError",
    "DepositReason",
    "DepositRequest",
    "RepositoryTicketClaims",
    "sha256",
]

# The `aud` of every deposit grant and repository enrolment ticket.
DEPOSIT_BROKER_AUDIENCE = "urn:data-director:deposit-broker"

# JOSE `typ` headers. Neither is the model grant's (`JWT`) or the model enrolment ticket's.
GRANT_TYPE = "dd-deposit+jwt"
TICKET_TYPE = "dd-repository-enrolment+jwt"
TICKET_PURPOSE = "repository-enrolment"

# A grant is for one request, made as soon as the approval is recorded: creating a draft and
# uploading the package takes seconds, not minutes.
GRANT_LIFETIME_S = 300
TICKET_LIFETIME_S = 120

# Claims of a deposit grant beside `aud`, `iat`, `exp`, `jti` and `dd_subject`.
CLAIM_REPOSITORY = "dd_repository"
CLAIM_TRANSPORT = "dd_transport"
CLAIM_BASE_URL = "dd_base_url"
CLAIM_TARGET = "dd_target"
CLAIM_PACKAGE_DIGEST = "dd_package_digest"
CLAIM_ITEM_DIGEST = "dd_item_digest"
CLAIM_APPROVAL = "dd_approval"
_GRANT_ONLY_CLAIMS = (
    CLAIM_REPOSITORY,
    CLAIM_TRANSPORT,
    CLAIM_BASE_URL,
    CLAIM_TARGET,
    CLAIM_PACKAGE_DIGEST,
    CLAIM_ITEM_DIGEST,
    CLAIM_APPROVAL,
)

# Where the harness asks the deposit broker for a draft, on the broker's loopback address. Never
# exposed through the reverse proxy.
DEPOSITS_PATH = "/deposits"
HEADER_GRANT = "X-DD-Deposit-Grant"
HEADER_REASON = "X-DD-Reason"

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
# The repository, by its re3data or DataCite identifier (dd_sdk.contract.base).
_REPOSITORY_ID = re.compile(REPOSITORY_ID_PATTERN)
_NAME = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class DepositReason(StrEnum):
    """Why the deposit broker refused, or the repository did not make, a draft. Sent in
    `X-DD-Reason` and recorded on a `deposit_failed` event; never the repository's own message,
    which may quote what was sent."""

    GRANT_MISSING = "grant-missing"
    GRANT_INVALID = "grant-invalid"
    GRANT_EXPIRED = "grant-expired"
    GRANT_USED = "grant-used"
    BODY_INVALID = "body-invalid"
    DIGEST_MISMATCH = "digest-mismatch"
    TRANSPORT_UNKNOWN = "transport-unknown"
    BASE_URL_NOT_ALLOWED = "base-url-not-allowed"
    ACCOUNT_MISSING = "account-missing"
    ACCOUNT_REJECTED = "account-rejected"
    TARGET_UNKNOWN = "target-unknown"
    ITEM_REJECTED = "item-rejected"
    REPOSITORY_UNAVAILABLE = "repository-unavailable"
    BROKER_UNAVAILABLE = "broker-unavailable"
    TICKET_MISSING = "ticket-missing"
    TICKET_INVALID = "ticket-invalid"
    TICKET_EXPIRED = "ticket-expired"
    TICKET_USED = "ticket-used"


class DepositGrantError(ValueError):
    """A claim set or a body does not have the deposit grant's shape. The message names the claim
    or the member, never its value."""


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _text(claims: Mapping[str, Any], name: str, token: str) -> str:
    value = claims.get(name)
    if not isinstance(value, str) or not value:
        raise DepositGrantError(f"the {token}'s {name} is missing or not a string")
    return value


def _number(claims: Mapping[str, Any], name: str, token: str) -> int:
    value = claims.get(name)
    if not isinstance(value, int) or isinstance(value, bool):
        raise DepositGrantError(f"the {token}'s {name} is missing or not an integer")
    return value


def _matching(claims: Mapping[str, Any], name: str, pattern: re.Pattern[str]) -> str:
    value = _text(claims, name, "grant")
    if not pattern.fullmatch(value):
        raise DepositGrantError(f"the grant's {name} is malformed")
    return value


@dataclass(frozen=True)
class DepositGrantClaims:
    """The claims of a deposit grant whose signature has been checked."""

    audience: str
    grant_id: str
    subject: str
    repository: str
    transport: str
    base_url: str
    target: str | None
    package_digest: str
    item_digest: str
    approval: str
    issued_at: int
    expires_at: int

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> DepositGrantClaims:
        if CLAIM_PURPOSE in claims:
            raise DepositGrantError(f"a deposit grant carries no {CLAIM_PURPOSE}")
        base_url = _text(claims, CLAIM_BASE_URL, "grant")
        if not base_url.startswith("https://"):
            raise DepositGrantError(f"the grant's {CLAIM_BASE_URL} is not https")
        target = claims.get(CLAIM_TARGET)
        if target is not None and (not isinstance(target, str) or not target):
            raise DepositGrantError(f"the grant's {CLAIM_TARGET} is not a string")
        issued_at = _number(claims, CLAIM_ISSUED_AT, "grant")
        expires_at = _number(claims, CLAIM_EXPIRES, "grant")
        if expires_at <= issued_at:
            raise DepositGrantError("the grant expires before it is issued")
        return cls(
            audience=_text(claims, CLAIM_AUDIENCE, "grant"),
            grant_id=_text(claims, CLAIM_TICKET_ID, "grant"),
            subject=_text(claims, CLAIM_SUBJECT, "grant"),
            repository=_matching(claims, CLAIM_REPOSITORY, _REPOSITORY_ID),
            transport=_matching(claims, CLAIM_TRANSPORT, _NAME),
            base_url=base_url,
            target=target,
            package_digest=_matching(claims, CLAIM_PACKAGE_DIGEST, _DIGEST),
            item_digest=_matching(claims, CLAIM_ITEM_DIGEST, _DIGEST),
            approval=_text(claims, CLAIM_APPROVAL, "grant"),
            issued_at=issued_at,
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class RepositoryTicketClaims:
    """The claims of a repository enrolment ticket whose signature has been checked."""

    audience: str
    ticket_id: str
    subject: str
    issued_at: int
    expires_at: int

    @classmethod
    def from_claims(cls, claims: Mapping[str, Any]) -> RepositoryTicketClaims:
        if claims.get(CLAIM_PURPOSE) != TICKET_PURPOSE:
            raise DepositGrantError(f"the ticket's {CLAIM_PURPOSE} is not {TICKET_PURPOSE}")
        for name in _GRANT_ONLY_CLAIMS:
            if name in claims:
                raise DepositGrantError(f"a ticket carries no {name}")
        issued_at = _number(claims, CLAIM_ISSUED_AT, "ticket")
        expires_at = _number(claims, CLAIM_EXPIRES, "ticket")
        if expires_at <= issued_at:
            raise DepositGrantError("the ticket expires before it is issued")
        return cls(
            audience=_text(claims, CLAIM_AUDIENCE, "ticket"),
            ticket_id=_text(claims, CLAIM_TICKET_ID, "ticket"),
            subject=_text(claims, CLAIM_SUBJECT, "ticket"),
            issued_at=issued_at,
            expires_at=expires_at,
        )


@dataclass(frozen=True)
class DepositRequest:
    """What the harness sends to `POST /deposits`: the rendered platform item and the RO-Crate
    package, each as the exact bytes whose digests the grant names, and the file name the package
    takes in the draft. JSON, with the bytes in base64: the package holds no data file, so it is
    small."""

    item: bytes
    package: bytes
    package_name: str

    def to_json(self) -> dict[str, str]:
        return {
            "item": base64.b64encode(self.item).decode("ascii"),
            "package": base64.b64encode(self.package).decode("ascii"),
            "package_name": self.package_name,
        }

    @classmethod
    def from_json(cls, body: Any) -> DepositRequest:
        if not isinstance(body, dict) or set(body) != {"item", "package", "package_name"}:
            raise DepositGrantError("the body is not a deposit request")
        name = body["package_name"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", name)
            or not name.endswith(".zip")
        ):
            raise DepositGrantError("the body's package_name is not a plain .zip file name")
        try:
            item = base64.b64decode(body["item"], validate=True)
            package = base64.b64decode(body["package"], validate=True)
        except (TypeError, ValueError) as exc:
            raise DepositGrantError("the body's item or package is not base64") from exc
        return cls(item=item, package=package, package_name=name)


@dataclass(frozen=True)
class DepositAnswer:
    """What the deposit broker answers when the repository made the draft: the repository's
    identifier for it, where a person opens it, and a DOI only if the repository reported one
    unasked (docs/specs/deposit.md, invariant 15)."""

    deposit_id: str
    draft_url: str
    doi: str | None = None

    def to_json(self) -> dict[str, str]:
        answer = {"deposit_id": self.deposit_id, "draft_url": self.draft_url}
        if self.doi:
            answer["doi"] = self.doi
        return answer

    @classmethod
    def from_json(cls, body: Any) -> DepositAnswer:
        if not isinstance(body, dict):
            raise DepositGrantError("the answer is not an object")
        deposit_id, draft_url = body.get("deposit_id"), body.get("draft_url")
        doi = body.get("doi")
        if not isinstance(deposit_id, str) or not deposit_id:
            raise DepositGrantError("the answer's deposit_id is missing")
        if not isinstance(draft_url, str) or not draft_url.startswith("https://"):
            raise DepositGrantError("the answer's draft_url is not an https URL")
        if doi is not None and not isinstance(doi, str):
            raise DepositGrantError("the answer's doi is not a string")
        return cls(deposit_id=deposit_id, draft_url=draft_url, doi=doi or None)
