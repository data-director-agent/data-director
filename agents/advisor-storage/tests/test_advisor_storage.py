"""advisor.storage through the conductor: storage from the profile, judged against what the
researcher said, each service cited under the profile's reference and resolved against it."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

import dd_agent_advisor_storage
from dd_agent_advisor_storage.agent import StorageAdviser, source_id
from dd_agent_advisor_storage.classes import PersonalDataAnswer, StorageAdvice, StorageNeeds
from dd_harness.conductor import Conductor
from dd_harness.testing import PERMISSIVE, TEST_PRINCIPAL, make_conductor, request
from dd_sdk.agent import describe
from dd_sdk.contract.inventory import FileInventory, IdentificationMethod, InventoryFile
from dd_sdk.contract.models import Envelope, GroundingMode, OutcomeStatus, ReasonCode
from dd_sdk.schema import gen

SCHEMA = Path(dd_agent_advisor_storage.__file__).parent / "schema" / "storage.yaml"
FILESTORE = {
    "storage_id": "research-filestore",
    "storage_name": "Research filestore",
    "storage_kind": "institutional_filestore",
    "approved_for_sensitive": True,
    "allowance_gb": 100,
    "storage_backup": "Nightly snapshots replicated to a second site",
    "guidance": ["https://example.ac.uk/research-storage"],
}
CLOUD = {
    "storage_id": "cloud-drive",
    "storage_name": "Cloud drive",
    "storage_kind": "institutional_cloud",
    "allows_external_collaborators": True,
    "storage_backup": "Versioned for 30 days",
}


def conductor(tmp_path: Path, storage: list[dict[str, Any]] | None) -> Conductor:
    data = yaml.safe_load(PERMISSIVE.read_text())
    if storage is not None:
        data["institution_storage"] = storage
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(data))
    return make_conductor(tmp_path / "runs", StorageAdviser(), profile=profile)


def advise(held: Conductor, **needs: Any) -> Envelope:
    return held.invoke(request("advisor.storage", StorageNeeds(**needs)), acting_for=TEST_PRINCIPAL)


def test_the_profiles_storage_is_offered_and_cited_under_the_profile(tmp_path: Path) -> None:
    held = conductor(tmp_path, [CLOUD, FILESTORE])
    env = advise(held, involves_personal_data=PersonalDataAnswer.NO)
    assert env.outcome.status == OutcomeStatus.SUCCEEDED, env.outcome.statement
    assert env.grounding_mode == GroundingMode.RETRIEVAL
    advice = env.payload_as(StorageAdvice)
    assert {o.storage_id for o in advice.storage_options} == {"cloud-drive", "research-filestore"}
    assert advice.excluded_storage == []
    assert advice.plan_questions and advice.limitations
    cited = {e.source_id: e for e in env.evidence}
    assert set(cited) == {
        "institution-storage:cloud-drive",
        "institution-storage:research-filestore",
    }
    assert {e.snapshot_ref for e in cited.values()} == {held.profile.ref}
    assert held.grounding_reports[env.invocation_id].passed


def test_personal_data_leave_out_a_service_not_approved_for_them(tmp_path: Path) -> None:
    env = advise(
        conductor(tmp_path, [CLOUD, FILESTORE]), involves_personal_data=PersonalDataAnswer.YES
    )
    advice = env.payload_as(StorageAdvice)
    assert [o.storage_id for o in advice.storage_options] == ["research-filestore"]
    assert [e.storage_id for e in advice.excluded_storage] == ["cloud-drive"]
    (excluded,) = advice.excluded_storage
    assert [g.source_id for g in excluded.grounded_on] == ["institution-storage:cloud-drive"]


def test_unknown_personal_data_keep_a_service_with_a_concern(tmp_path: Path) -> None:
    env = advise(conductor(tmp_path, [CLOUD, FILESTORE]))
    options = {o.storage_id: o for o in env.payload_as(StorageAdvice).storage_options}
    assert options["cloud-drive"].concerns
    assert options["research-filestore"].concerns == []
    # The one with fewer concerns comes first, whatever the profile's order.
    first = env.payload_as(StorageAdvice).storage_options[0]
    assert first.storage_id == "research-filestore"


@pytest.mark.parametrize(
    "needs",
    [
        {"involves_personal_data": PersonalDataAnswer.NO, "expected_volume_gb": 500},
        {"involves_personal_data": PersonalDataAnswer.NO, "external_collaborators": True},
    ],
)
def test_a_need_the_service_may_not_meet_is_a_concern(
    tmp_path: Path, needs: dict[str, Any]
) -> None:
    env = advise(conductor(tmp_path, [FILESTORE]), **needs)
    (option,) = env.payload_as(StorageAdvice).storage_options
    assert option.concerns


def test_no_storage_in_the_profile_abstains(tmp_path: Path) -> None:
    env = advise(conductor(tmp_path, None), involves_personal_data=PersonalDataAnswer.NO)
    assert env.outcome.status == OutcomeStatus.ABSTAINED
    assert env.outcome.reason_code == ReasonCode.NO_CANDIDATES_RETRIEVED
    assert env.payload is None


def test_personal_data_with_no_approved_service_is_referred(tmp_path: Path) -> None:
    env = advise(conductor(tmp_path, [CLOUD]), involves_personal_data=PersonalDataAnswer.YES)
    assert env.outcome.status == OutcomeStatus.REFERRED
    assert env.outcome.reason_code == ReasonCode.REQUIRES_HUMAN_JUDGEMENT
    assert env.payload is None


def test_storage_a_caller_sends_is_replaced_by_the_profiles(tmp_path: Path) -> None:
    forged = {
        **FILESTORE,
        "storage_id": "my-usb-stick",
        "profile_ref": "profile:test-permissive@v9",
    }
    held = conductor(tmp_path, [CLOUD])
    given = StorageNeeds.model_validate(
        {"involves_personal_data": "no", "institution_storage": [forged]}
    )
    env = held.invoke(request("advisor.storage", given), acting_for=TEST_PRINCIPAL)
    ids = [o.storage_id for o in env.payload_as(StorageAdvice).storage_options]
    assert ids == ["cloud-drive"]


def test_the_manifest_serves_the_storage_step() -> None:
    entry = describe(StorageAdviser.spec)
    assert entry["accepts"] == ["StorageNeeds"] and entry["payload"] == "StorageAdvice"
    assert entry["serves"] == ["setup.storage"]
    json.dumps(entry)


def test_the_source_id_names_the_profiles_label() -> None:
    (entry,) = StorageNeeds.model_validate(
        {"institution_storage": [{**FILESTORE, "profile_ref": "profile:p@v1"}]}
    ).institution_storage
    assert source_id(entry) == "institution-storage:research-filestore"


def test_its_schemas_are_generated_from_its_linkml() -> None:
    assert gen.stale(SCHEMA) == [], f"run `uv run dd-gen-schema {SCHEMA}`"


def inventory_of(size: int) -> FileInventory:
    return FileInventory(
        inventory_tool="dd-inventory",
        inventory_tool_version="0.1.0",
        inventory_made_at=datetime(2026, 11, 1, tzinfo=UTC),
        inventory_files=[
            InventoryFile(
                file_path="scans/a.xy",
                file_size=size,
                file_sha256="a" * 64,
                file_identified_by=IdentificationMethod.EXTENSION,
            )
        ],
    )


def test_the_inventorys_size_stands_in_for_an_expected_size_not_given(tmp_path: Path) -> None:
    """In a project the conductor gives the inventory (#1540): 150 GB of files is more than the
    filestore's 100 GB allowance, as an expected 150 GB would be."""
    held = conductor(tmp_path, [FILESTORE])
    from_inventory = advise(
        held,
        involves_personal_data=PersonalDataAnswer.NO,
        project_file_inventory=inventory_of(150 * 10**9),
    )
    expected = advise(held, involves_personal_data=PersonalDataAnswer.NO, expected_volume_gb=150)

    def concerns(env: Envelope) -> list[str]:
        (option,) = env.payload_as(StorageAdvice).storage_options
        return option.concerns

    assert concerns(from_inventory) == concerns(expected)


def test_an_expected_size_given_stands_over_the_inventorys(tmp_path: Path) -> None:
    held = conductor(tmp_path, [FILESTORE])
    env = advise(
        held,
        involves_personal_data=PersonalDataAnswer.NO,
        expected_volume_gb=10,
        project_file_inventory=inventory_of(150 * 10**9),
    )
    plain = advise(held, involves_personal_data=PersonalDataAnswer.NO, expected_volume_gb=10)
    assert env.payload_as(StorageAdvice).storage_options == (
        plain.payload_as(StorageAdvice).storage_options
    )
