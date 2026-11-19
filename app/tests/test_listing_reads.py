"""What a listing asks of the project store does not grow with the number of projects (#1257):
the projects a person may read, and their deleted conversations, are decided from one read."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from support import a_file_inventory, configure_env, new_governance

from dd_app.governance import Governance
from dd_harness.project_files import FileProjectLog
from dd_harness.projects import Projects
from dd_harness.testing import TEST_PRINCIPAL, CountingLog
from dd_sdk.contract.models import Principal

SOMEONE_ELSE = Principal(principal_id="https://orcid.org/0000-0002-1694-233X", name="Someone Else")


@pytest.fixture
def governance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Governance]:
    configure_env(monkeypatch, tmp_path)
    yield from new_governance()


def _reads(governance: Governance, root: Path, count: int) -> dict[str, dict[str, int]]:
    """How many reads of the project log each listing makes, with `count` projects of the
    person's, one of them with a deleted conversation, and as many of someone else's."""
    log = CountingLog(FileProjectLog(root))
    projects = Projects(log.as_log())
    governance.projects = projects
    for n in range(count):
        project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test")
        if n % 2:
            projects.add_inventory(
                project_id, a_file_inventory(f"{n}.csv"), acted_for=TEST_PRINCIPAL, caused_by="t"
            )
        projects.create(acted_for=SOMEONE_ELSE, caused_by="test")
    conversation_id = projects.start_conversation(
        project_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    projects.delete_conversation(
        project_id, conversation_id, acted_for=TEST_PRINCIPAL, caused_by="test"
    )
    listings: dict[str, Callable[[], object]] = {
        "projects": lambda: governance.projects_for(TEST_PRINCIPAL, limit=200),
        "conversations": lambda: governance.conversations(TEST_PRINCIPAL),
        "runs": lambda: governance.runs(TEST_PRINCIPAL),
    }
    found = {}
    for name, listing in listings.items():
        log.calls.clear()
        listing()
        found[name] = dict(log.calls)
    return found


def test_a_listing_reads_the_project_store_as_often_for_many_projects_as_for_few(
    governance: Governance, tmp_path: Path
) -> None:
    few = _reads(governance, tmp_path / "few", 2)
    many = _reads(governance, tmp_path / "many", 30)
    assert few == many
    assert many == {
        "projects": {"logs_naming": 1},
        "conversations": {"logs_naming": 1},
        "runs": {"logs_naming": 1},
    }
    assert len(governance.projects_for(TEST_PRINCIPAL, limit=200).items) == 15
