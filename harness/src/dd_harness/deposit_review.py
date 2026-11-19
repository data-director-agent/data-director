"""The pause before packaging: what a person must decide, and confirm, before a project's deposit
package is built (docs/specs/deposit.md, "The pause before packaging"; Blueprint C2).

`review` reads the project log and writes nothing. It lists, from the inventory the project holds
now:

- each name-level hint (`dd_sdk.inventory_hints`): a file whose folder, file or field names, size
  or digest call for a person to look, such as field notes, a table of coordinates, a folder of
  someone else's material or an agreement;
- each personal-data finding the inventory command recorded (`inventory_personal_data`,
  docs/specs/personal-data.md).

Each is an item a person decides, with the decision they made last, if it still stands. The
review also says whether a person has confirmed the checks C2 asks for (ethics approval, data
protection advice and third-party rights) against this inventory, and what the review did not
check. The deposit check (`dd_harness.deposit.validate`) carries each open item, and a missing
confirmation, as a warning; the package is not built while any is open.

`decide_item` and `confirm` record a person's decision and confirmation in the project log. An
agent never decides: nothing here is reachable from a run, and only a way in that names the
person signed in calls them.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Final, Literal
from urllib.parse import quote

from dd_harness.projects import (
    DEPOSIT_CHECKS_CONFIRMED,
    DEPOSIT_ITEM_DECIDED,
    INVENTORY_ADDED,
    ProjectError,
)
from dd_harness.shacl import DD, WARNING, Result
from dd_harness.storage import DepositSource
from dd_sdk.contract.models import InventoryFile, Principal
from dd_sdk.inventory_hints import hints

# The constraint components of the review's results in the validation report.
DECISION_CHECK: Final = DD + "PersonDecisionConstraintComponent"
CONFIRMATION_CHECK: Final = DD + "DepositConfirmationConstraintComponent"
REVIEW_CHECKS: Final = frozenset({DECISION_CHECK, CONFIRMATION_CHECK})
# The longest note a person may give with a decision, in characters.
NOTE_MAX_LENGTH: Final = 2000

type Source = Literal["name", "finding"]


class ItemDecision(StrEnum):
    """What a person decided about an item."""

    KEEP = "keep"
    """Checked: the file is deposited as it is."""
    LEAVE_OUT = "leave_out"
    """The file is left out of the deposit."""
    CHANGE = "change"
    """A changed copy, such as a redacted or generalised one, is deposited instead."""


# What a person confirms before a deposit, by identifier, in the words they confirm.
CONFIRMATIONS: Final = {
    "ethics_approval": (
        "The ethics approvals that apply to these data are in place, and depositing them is "
        "within what they allow."
    ),
    "data_protection": (
        "Data protection advice has been taken for any data about living people, or the data hold "
        "none."
    ),
    "third_party_rights": (
        "Material from others may be shared on the terms it came with, and every agreement the "
        "data come under is still in force and allows the deposit."
    ),
}

NOT_READ: Final = (
    "Data Director read the inventory's folder, file and field names, sizes and digests, never "
    "the files' contents: a file not listed may still hold personal data, sensitive locations or "
    "someone else's material."
)
NO_DETECTOR: Final = (
    "No personal-data detector ran on this inventory, so no values in the files were checked for "
    "direct identifiers. Making the inventory again with dd-inventory runs one."
)
NOTHING_DETECTED: Final = (
    "The personal-data detector found no direct identifiers in the rows and names it checked. "
    "This does not mean the data hold no personal data: free text beyond the files it read, other "
    "formats, indirect identifiers and rows beyond the sample were not checked."
)
NO_INVENTORY: Final = "The project holds no inventory, so no file was checked."


class UnknownItemError(ProjectError):
    """The decision names no item the deposit check lists for the project now."""


@dataclass(frozen=True)
class ReviewItem:
    """One thing a person decides before packaging: a file, and why it calls for a look."""

    item_id: str
    source: Source
    kind: str
    path: str
    question: str
    matched: str | None = None
    column: str | None = None
    related_paths: tuple[str, ...] = ()
    file_sha256: str | None = None
    # The decision that stands for this item, as the log records it, or None.
    decision: Mapping[str, Any] | None = None

    def described(self) -> dict[str, Any]:
        """The item as a decision on it records it, so that the log reads on its own."""
        found: dict[str, Any] = {
            "source": self.source,
            "kind": self.kind,
            "path": self.path,
            "question": self.question,
        }
        for key in ("matched", "column", "file_sha256"):
            if getattr(self, key) is not None:
                found[key] = getattr(self, key)
        if self.related_paths:
            found["related_paths"] = list(self.related_paths)
        return found


@dataclass(frozen=True)
class Review:
    """What a person must decide and confirm before the project is packaged."""

    inventory_digest: str | None
    items: tuple[ReviewItem, ...]
    # The confirmation that stands for this inventory, as the log records it, or None.
    confirmation: Mapping[str, Any] | None
    not_checked: tuple[str, ...] = field(default_factory=tuple)

    @property
    def open_items(self) -> tuple[ReviewItem, ...]:
        return tuple(item for item in self.items if item.decision is None)

    @property
    def paused(self) -> bool:
        """Whether the package waits on a person: an item is undecided, or the checks are not
        confirmed."""
        return bool(self.open_items) or self.confirmation is None

    def results(self, project_id: str) -> list[Result]:
        """Each open item, and a missing confirmation, as a warning of the validation report."""
        found = [
            Result(
                WARNING,
                f"{item.path}: {item.question} Decide before packaging.",
                _item_iri(project_id, item.path),
                DECISION_CHECK,
            )
            for item in self.open_items
        ]
        if self.confirmation is None:
            found.append(
                Result(
                    WARNING,
                    "Confirm that ethics approval, data protection advice and the rights to any "
                    "third-party material have been checked before packaging.",
                    f"urn:uuid:{project_id}",
                    CONFIRMATION_CHECK,
                )
            )
        return found

    def to_document(self) -> dict[str, Any]:
        """The review as the app draws it and the package records it."""
        return {
            "inventory_digest": self.inventory_digest,
            "items": [
                {
                    "item_id": item.item_id,
                    "source": item.source,
                    "kind": item.kind,
                    "path": item.path,
                    "question": item.question,
                    "matched": item.matched,
                    "column": item.column,
                    "related_paths": list(item.related_paths),
                    "file_sha256": item.file_sha256,
                    "decision": item.decision,
                }
                for item in self.items
            ],
            "confirmation": self.confirmation,
            "statements": [{"id": k, "text": v} for k, v in CONFIRMATIONS.items()],
            "not_checked": list(self.not_checked),
        }


def review(projects: DepositSource, project_id: str) -> Review:
    """What a person must decide and confirm before the project is packaged, from the inventory
    it holds now and the decisions in its log. Writes nothing."""
    events = projects.events(project_id)
    added = [e for e in events if e["event"] == INVENTORY_ADDED]
    digest = str(added[-1]["digest"]) if added else None
    inventory = projects.inventory(project_id) if added else None
    if inventory is None:
        return Review(None, (), _confirmation(events, None), (NO_INVENTORY,))
    decided = {
        e["item_id"]: e
        for e in events
        if e["event"] == DEPOSIT_ITEM_DECIDED and e.get("inventory_digest") == digest
    }
    items = tuple(_with_decision(item, decided.get(item.item_id)) for item in _items(inventory))
    findings = inventory.get("inventory_personal_data")
    not_checked: tuple[str, ...] = (NOT_READ,)
    if findings is None:
        not_checked += (NO_DETECTOR,)
    elif not findings:
        not_checked += (NOTHING_DETECTED,)
    return Review(digest, items, _confirmation(events, digest), not_checked)


def decide_item(
    projects: DepositSource,
    project_id: str,
    item_id: str,
    decision: ItemDecision,
    note: str | None,
    *,
    acted_for: Principal,
    caused_by: str,
) -> ReviewItem:
    """Record a person's decision on an item the deposit check lists now, and return the item
    with it. A later decision on the same item replaces it.

    Raises `UnknownItemError` for an item the check does not list, `ProjectError` for a note
    over `NOTE_MAX_LENGTH` and for an unknown project."""
    if note is not None and len(note) > NOTE_MAX_LENGTH:
        raise ProjectError(f"a note is at most {NOTE_MAX_LENGTH} characters")
    found = review(projects, project_id)
    item = next((i for i in found.items if i.item_id == item_id), None)
    if item is None:
        raise UnknownItemError(
            f"the deposit check lists no item {item_id!r} for this project's current inventory"
        )
    detail: dict[str, Any] = {
        "item_id": item_id,
        "item": item.described(),
        "decision": ItemDecision(decision).value,
        "inventory_digest": found.inventory_digest,
    }
    if note and note.strip():
        detail["note"] = note.strip()
    projects.record_item_decision(project_id, detail, acted_for=acted_for, caused_by=caused_by)
    return review(projects, project_id).items[found.items.index(item)]


def confirm(
    projects: DepositSource,
    project_id: str,
    confirmed: Collection[str],
    *,
    acted_for: Principal,
    caused_by: str,
) -> Mapping[str, Any]:
    """Record a person's confirmation of every statement in `CONFIRMATIONS`, against the
    inventory the project holds now, and return it as the log records it.

    Raises `ProjectError` unless `confirmed` names every statement and no other, and for an
    unknown project."""
    if set(confirmed) != set(CONFIRMATIONS):
        missing = ", ".join(sorted(set(CONFIRMATIONS) - set(confirmed))) or "none"
        unknown = ", ".join(sorted(set(confirmed) - set(CONFIRMATIONS))) or "none"
        raise ProjectError(
            "every statement must be confirmed together "
            f"(not confirmed: {missing}; not a statement: {unknown})"
        )
    digest = review(projects, project_id).inventory_digest
    projects.record_confirmation(
        project_id,
        {
            "statements": [{"id": k, "text": v} for k, v in CONFIRMATIONS.items()],
            "inventory_digest": digest,
        },
        acted_for=acted_for,
        caused_by=caused_by,
    )
    confirmation = review(projects, project_id).confirmation
    assert confirmation is not None  # just recorded against this inventory
    return confirmation


def _items(inventory: Mapping[str, Any]) -> list[ReviewItem]:
    files = [InventoryFile.model_validate(f) for f in inventory.get("inventory_files") or []]
    digests = {f.file_path: f.file_sha256 for f in files}
    found = [
        ReviewItem(
            item_id="",
            source="name",
            kind=hint.kind.value,
            path=hint.path,
            question=hint.question,
            matched=hint.matched,
            related_paths=hint.related_paths,
            file_sha256=digests.get(hint.path),
        )
        for hint in hints(files)
    ]
    for finding in inventory.get("inventory_personal_data") or []:
        path = finding["finding_file"]
        found.append(
            ReviewItem(
                item_id="",
                source="finding",
                kind=finding["finding_kind"],
                path=path,
                question=_finding_question(finding),
                column=finding.get("finding_column"),
                file_sha256=digests.get(path),
            )
        )
    return [_identified(item) for item in found]


def _identified(item: ReviewItem) -> ReviewItem:
    """The item, identified by what it is about: its source, kind, file, column and the file's
    digest. A changed file is a new item, so a decision on the old one does not carry over."""
    key = json.dumps(
        [item.source, item.kind, item.path, item.column, item.file_sha256], ensure_ascii=False
    )
    return replace(item, item_id=hashlib.sha256(key.encode("utf-8")).hexdigest()[:24])


def _finding_question(finding: Mapping[str, Any]) -> str:
    where = {
        "column": f"the values of the column {finding.get('finding_column')}",
        "field name": f"the field name {finding.get('finding_column')}",
        "file name": "its name",
        "text": "its text",
    }.get(finding["finding_target"], "it")
    return (
        f"Possible personal data ({finding['finding_kind']}) was found in {where}, with "
        f"{finding['finding_confidence']} confidence. The inventory does not include the values. "
        "Check them, and talk to your data steward or ethics contact about how they should be "
        "handled."
    )


def _with_decision(item: ReviewItem, event: Mapping[str, Any] | None) -> ReviewItem:
    if event is None:
        return item
    decision = {
        "decision": event["decision"],
        "note": event.get("note"),
        "decided_by": event["acted_for"],
        "decided_at": event["at"],
    }
    return replace(item, decision=decision)


def _confirmation(events: Sequence[Mapping[str, Any]], digest: str | None) -> dict[str, Any] | None:
    """The last confirmation made against the inventory `digest`, or None."""
    found = [
        e
        for e in events
        if e["event"] == DEPOSIT_CHECKS_CONFIRMED and e.get("inventory_digest") == digest
    ]
    if not found:
        return None
    last = found[-1]
    return {
        "statements": last["statements"],
        "confirmed_by": last["acted_for"],
        "confirmed_at": last["at"],
    }


def _item_iri(project_id: str, path: str) -> str:
    return f"urn:uuid:{project_id}#file/{quote(path)}"
