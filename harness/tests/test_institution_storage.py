"""The profile's `institution_storage`: the storage services a deployment names as its
institution's, read with the profile and checked when an agent cites them
(docs/specs/policy-and-identity.md)."""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from dd_harness import institution_repositories, institution_storage, profile_vouched
from dd_harness.policy import PolicyError, Profile
from dd_harness.sources import Sources, check
from dd_harness.testing import PERMISSIVE
from dd_sdk.contract.facts import StorageKind
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, content_hash

FILESTORE = {
    "storage_id": "research-filestore",
    "storage_name": "Research filestore",
    "storage_kind": "institutional_filestore",
    "approved_for_sensitive": True,
    "allowance_gb": 10000,
    "charges_for_storage": False,
    "storage_backup": "Nightly snapshots, replicated to a second site",
    "guidance": ["https://example.ac.uk/research-storage"],
}
REPOSITORY = {"repository_id": "r3d100012124"}


def profile(storage: Any, repositories: Any = None) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data["institution_storage"] = storage
    data["institution_repositories"] = repositories
    return Profile.from_mapping(data, source="test", digest="0" * 64)


def test_the_profile_names_its_storage_by_its_own_label() -> None:
    held = profile([FILESTORE])
    (entry,) = held.institution_storage
    assert entry.storage_id == "research-filestore"
    assert entry.storage_kind is StorageKind.INSTITUTIONAL_FILESTORE
    assert entry.approved_for_sensitive is True
    assert entry.profile_ref == held.ref
    assert profile(None).institution_storage == ()


@pytest.mark.parametrize(
    "entries",
    [
        [{**FILESTORE, "storage_id": "Research Filestore"}],
        [{key: value for key, value in FILESTORE.items() if key != "storage_id"}],
        [{key: value for key, value in FILESTORE.items() if key != "storage_name"}],
        [FILESTORE, FILESTORE],
        [{**FILESTORE, "cost_per_tb": 50}],
        [{**FILESTORE, "profile_ref": "profile:other@v1"}],
        [{**FILESTORE, "storage_kind": "usb stick"}],
        [{**FILESTORE, "allowance_gb": -1}],
        {"storage_id": "research-filestore"},
        ["research-filestore"],
    ],
)
def test_a_malformed_entry_stops_the_profile_loading(entries: Any) -> None:
    with pytest.raises(PolicyError):
        profile(entries)


def test_the_source_check_resolves_storage_and_repositories_under_one_profile() -> None:
    held = profile([FILESTORE], [REPOSITORY])
    (document,) = institution_storage.documents(held.institution_storage)
    evidence = {
        "source_id": "institution-storage:research-filestore",
        "snapshot_ref": held.ref,
        "canonicalisation": DOCUMENT_CANONICALISATION,
        "content_hash": content_hash(document, DOCUMENT_CANONICALISATION),
    }
    vouched = {**institution_repositories.vouched(held), **institution_storage.vouched(held)}
    assert set(vouched) == {"institution:r3d100012124", "institution-storage:research-filestore"}
    with_profile = Sources().with_resolvers(profile_vouched.resolvers(held.ref, vouched))
    assert check({"evidence": [evidence]}, with_profile).verified == 1
    forged = {**evidence, "content_hash": "f" * 64}
    assert not check({"evidence": [forged]}, with_profile).passed
    assert check({"evidence": [evidence]}, Sources()).unresolved
    assert profile_vouched.resolvers(held.ref, {}) == {}
