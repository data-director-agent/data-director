"""Depositing a draft through a repository's API, after a person approves it (docs/specs/deposit.md,
Depositing through an API; invariants 11 to 15 and 17 to 19).

`approve_and_deposit` is the harness's action, not an agent's: no agent starts it and no agent's
output chooses what it sends. It runs only on a person's request, and, in order:

1. checks that the package named is the project's latest RO-Crate package, built from a valid
   report, and that nothing the package was built from has changed since;
2. checks that the repository chosen has a `deposit` block in its override, that the profile
   offers its transport, that the transport is installed, and that the deployment has a deposit
   broker;
3. renders the approved DataCite record into the platform's item and keeps it by its digest, as
   a package `derived_from` the RO-Crate package;
4. records the person's approval as `deposit_approved`, refused if the package was already
   deposited in the repository, or is being deposited;
5. mints a deposit grant naming exactly those bytes, and asks the deposit broker for the draft;
6. records the outcome: `deposit_recorded` with the draft's URL and identifier, or
   `deposit_failed` with a status and a reason code. A failure is an outcome, not an exception,
   and trying again needs a new approval.

Steps 1 and 2 refuse with `DepositRefusedError` and record nothing, since nothing was approved.
Nothing sent publishes the draft, reserves a DOI or uploads a data file (invariant 14): the
researcher adds the files and publishes in the repository's own interface.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from dd_harness.deposit_broker import DepositBroker, DepositRefusal
from dd_harness.deposit_record import datacite_attributes
from dd_harness.projects import (
    DEPOSIT_APPROVED,
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_FAILED,
    DEPOSIT_ITEM_DECIDED,
    DEPOSIT_RECORDED,
    DOCUMENT_VERSION_DECIDED,
    INVENTORY_ADDED,
    PACKAGE_BUILT,
    REPOSITORY_CHOSEN,
    RO_CRATE,
    package_format,
)
from dd_harness.projects.stewarding import pause_of
from dd_harness.requirements import Requirements
from dd_harness.storage import DepositSource
from dd_sdk.contract.models import DepositConnector, Principal
from dd_sdk.deposit_grant import DepositRequest
from dd_sdk.transports import Transport

# Events after which a package no longer shows the project as it is: an approved version, an
# inventory, a repository choice or a decision before packaging (TODO(#649) for the rest).
_CHANGES = frozenset(
    {
        INVENTORY_ADDED,
        REPOSITORY_CHOSEN,
        DOCUMENT_VERSION_DECIDED,
        DEPOSIT_ITEM_DECIDED,
        DEPOSIT_CHECKS_CONFIRMED,
    }
)


class Refusal(StrEnum):
    """Why a deposit was refused before anything was approved or sent."""

    NO_REPOSITORY = "no-repository"
    BY_HAND = "by-hand"
    NOT_OFFERED = "transport-not-offered"
    NOT_INSTALLED = "transport-not-installed"
    NO_BROKER = "deposit-broker-unset"
    UNKNOWN_PACKAGE = "unknown-package"
    NOT_LATEST = "not-latest-package"
    STALE = "package-stale"
    NO_RECORD = "no-metadata-record"
    # A data steward paused the project (docs/specs/stewardship.md, invariant 8).
    PAUSED = "project-paused"


class DepositRefusedError(Exception):
    """The deposit cannot be approved; nothing was recorded or sent."""

    def __init__(self, refusal: Refusal, message: str) -> None:
        super().__init__(message)
        self.refusal = refusal


@dataclass(frozen=True)
class Connection:
    """How the project's repository is deposited to: through `connector`, or by hand when it is
    None, and why not through an API when it could be."""

    repository_id: str
    repository_name: str
    connector: DepositConnector | None
    unavailable: Refusal | None = None

    @property
    def available(self) -> bool:
        return self.connector is not None and self.unavailable is None


def connection(
    projects: DepositSource,
    project_id: str,
    *,
    requirements: Requirements,
    offered: frozenset[str],
    transports: Mapping[str, Transport],
    broker: DepositBroker | None,
) -> Connection | None:
    """How the repository the project chose last is deposited to, or None if it chose none."""
    chosen = projects.requirements(project_id)
    if chosen is None:
        return None
    repository_id, name = chosen["repository_id"], chosen["repository_name"]
    connector = requirements.connector(repository_id)
    if connector is None:
        return Connection(repository_id, name, None, Refusal.BY_HAND)
    unavailable = None
    if connector.transport not in offered:
        unavailable = Refusal.NOT_OFFERED
    elif connector.transport not in transports:
        unavailable = Refusal.NOT_INSTALLED
    elif broker is None:
        unavailable = Refusal.NO_BROKER
    return Connection(repository_id, name, connector, unavailable)


_REFUSED = {
    Refusal.BY_HAND: "{name} is deposited to by hand: the deployment names no API for it.",
    Refusal.NOT_OFFERED: "This deployment does not offer depositing to {name} through its API.",
    Refusal.NOT_INSTALLED: "The transport {name} is deposited through is not installed.",
    Refusal.NO_BROKER: "This deployment holds no repository accounts, so it cannot deposit "
    "to {name} for you.",
}


def deposits(projects: DepositSource, project_id: str) -> list[dict[str, Any]]:
    """Each deposit approved in the project, oldest first, with its outcome if it has one."""
    events = projects.events(project_id)
    outcomes = {
        e["approval"]: e for e in events if e["event"] in (DEPOSIT_RECORDED, DEPOSIT_FAILED)
    }
    return [
        {"approval": e, "outcome": outcomes.get(e["event_id"])}
        for e in events
        if e["event"] == DEPOSIT_APPROVED
    ]


@dataclass(frozen=True)
class DepositSetup:
    """What the deployment gives a deposit to work with: the transports its profile `offered`,
    those `transports` that are installed, and the deposit `broker`, if it holds one."""

    offered: frozenset[str]
    transports: Mapping[str, Transport]
    broker: DepositBroker | None


def approve_and_deposit(
    projects: DepositSource,
    project_id: str,
    digest: str,
    *,
    requirements: Requirements,
    setup: DepositSetup,
    acted_for: Principal,
    caused_by: str,
) -> dict[str, Any]:
    """Approve the deposit of the package `digest` in the project's repository, as `acted_for`,
    and make the draft. Returns the outcome event, `deposit_recorded` or `deposit_failed`.

    Raises `DepositRefusedError` when nothing may be approved (a project a data steward paused
    included), `DepositInProgressError` when the
    package was already deposited in the repository or is being deposited, and `ProjectError`
    for an unknown or deleted project."""
    if (held := pause_of(projects.events(project_id))) is not None:
        raise DepositRefusedError(
            Refusal.PAUSED, f"A data steward paused this project: {held['reason']}"
        )
    broker, transports = setup.broker, setup.transports
    found = connection(
        projects,
        project_id,
        requirements=requirements,
        offered=setup.offered,
        transports=transports,
        broker=broker,
    )
    if found is None:
        raise DepositRefusedError(Refusal.NO_REPOSITORY, "No repository has been chosen.")
    if found.unavailable is not None or found.connector is None or broker is None:
        refusal = found.unavailable or Refusal.BY_HAND
        raise DepositRefusedError(refusal, _REFUSED[refusal].format(name=found.repository_name))
    connector = found.connector
    transport = transports[connector.transport]
    _check_package(projects.events(project_id), digest)
    record = projects.metadata_record(project_id)
    try:
        attributes = datacite_attributes(record["document_text"]) if record else None
    except ValueError:
        attributes = None
    if attributes is None:
        raise DepositRefusedError(
            Refusal.NO_RECORD, "The project has no approved DataCite metadata record to send."
        )
    package = projects.package(project_id, digest)
    if package is None:
        raise DepositRefusedError(Refusal.UNKNOWN_PACKAGE, "The project built no such package.")

    item = transport.render(attributes, connector.target)
    item_digest = projects.record_package(
        project_id,
        item.content,
        about={
            "format": transport.format,
            "media_type": transport.media_type,
            "derived_from": digest,
            "unplaced": list(item.unplaced),
        },
        acted_for=acted_for,
        caused_by=caused_by,
    )
    named = {
        "digest": digest,
        "format": RO_CRATE,
        "item_digest": item_digest,
        "item_format": transport.format,
        "repository_id": found.repository_id,
        "repository_name": found.repository_name,
        "transport": connector.transport,
    }
    approval = projects.approve_deposit(
        project_id,
        {
            **named,
            "base_url": connector.base_url,
            **({"target": connector.target} if connector.target else {}),
            "sandbox": bool(connector.sandbox),
        },
        acted_for=acted_for,
        caused_by=caused_by,
    )
    grant = broker.minter.mint(
        acting_for=acted_for,
        repository=found.repository_id,
        connector=connector,
        package_digest=digest,
        item_digest=item_digest,
        approval=approval["event_id"],
    )
    answer = broker.create(
        grant,
        DepositRequest(
            item=item.content, package=package, package_name=f"ro-crate-{digest[:12]}.zip"
        ),
    )
    outcome: dict[str, Any] = {"approval": approval["event_id"], **named}
    if isinstance(answer, DepositRefusal):
        outcome |= {"status": answer.status, "reason": answer.reason.value}
        recorded = False
    else:
        outcome |= {
            "deposit_id": answer.deposit_id,
            "draft_url": answer.draft_url,
            "unplaced": list(item.unplaced),
        }
        if answer.doi:
            outcome["doi"] = answer.doi
        recorded = True
    return projects.record_deposit_outcome(
        project_id, outcome, recorded=recorded, acted_for=acted_for, caused_by=caused_by
    )


def _check_package(events: list[dict[str, Any]], digest: str) -> None:
    """That `digest` is the latest RO-Crate package and nothing it was built from has changed."""
    built = [
        (n, e)
        for n, e in enumerate(events)
        if e["event"] == PACKAGE_BUILT and package_format(e) == RO_CRATE
    ]
    if not any(e["digest"] == digest for _, e in built):
        raise DepositRefusedError(Refusal.UNKNOWN_PACKAGE, "The project built no such package.")
    position, latest = built[-1]
    if latest["digest"] != digest:
        raise DepositRefusedError(
            Refusal.NOT_LATEST,
            "A newer package has been built since this one; deposit the newest.",
        )
    if any(e["event"] in _CHANGES for e in events[position + 1 :]):
        raise DepositRefusedError(
            Refusal.STALE,
            "The project has changed since the package was built; build it again first.",
        )


def summary(deposit: Mapping[str, Any]) -> dict[str, Any]:
    """What the app shows of one deposit: no principal beyond its name, and nothing that is not
    in the project log already."""
    approval, outcome = deposit["approval"], deposit.get("outcome")
    shown: dict[str, Any] = {
        "approved_at": approval["at"],
        "approved_by": approval["acted_for"].get("name"),
        "digest": approval["digest"],
        "repository_name": approval["repository_name"],
        "transport": approval["transport"],
        "sandbox": bool(approval.get("sandbox")),
        "state": "pending"
        if outcome is None
        else ("recorded" if outcome["event"] == DEPOSIT_RECORDED else "failed"),
    }
    if outcome is not None:
        for key in ("draft_url", "deposit_id", "doi", "reason", "status", "unplaced"):
            if key in outcome:
                shown[key] = outcome[key]
    return shown
