"""Which standard's set a chosen repository is checked against, and why
(docs/specs/deposit.md, invariant 5; #1362)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from requirement_sets import ELSEWHERE, ORDA, override, pinned, standard, write

from dd_harness.projects import ProjectError, ProjectStore
from dd_harness.requirements import RequirementsError, load_requirements
from dd_harness.testing import TEST_PRINCIPAL

OAI_DC = "http://www.openarchives.org/OAI/2.0/oai_dc/"
DATACITE = "http://datacite.org/schema/kernel-4"


def dublin_core(**changes: Any) -> dict[str, Any]:
    return standard(
        requirement_set_id="dublin-core",
        title="Dublin Core (OAI-DC)",
        conforms_to=OAI_DC,
        re3data_names=["Dublin Core"],
        fields=[{"property": "title", "obligation": "required"}],
        **changes,
    )


def sets(
    tmp_path: Path, *extra: tuple[str, dict[str, Any]], preference: list[str] | None = None
) -> Path:
    root = write(
        tmp_path / "repositories", ("standards", standard()), ("standards", dublin_core()), *extra
    )
    if preference is not None:
        (root / "standard_preference.yaml").write_text(yaml.safe_dump({"preference": preference}))
    return root


@pytest.mark.parametrize(
    ("declared", "reason", "set_id"),
    [
        (["Dublin Core"], "declared", "dublin-core"),
        (["DataCite Metadata Schema"], "declared", "datacite-4"),
        (["Dublin Core", "DataCite Metadata Schema"], "declared_several", "datacite-4"),
        ([], "fallback", "datacite-4"),
        (["DDI"], "fallback", "datacite-4"),
    ],
)
def test_a_choice_names_its_standard_and_why(
    tmp_path: Path, declared: list[str], reason: str, set_id: str
) -> None:
    resolved = load_requirements(sets(tmp_path)).resolve(ELSEWHERE, "Elsewhere", declared)
    assert resolved.standard.requirement_set.requirement_set_id == set_id
    assert resolved.standard_reason == reason
    # What was assumed is said: a fallback or a pick among several warns; one declared does not.
    assumed = [w for w in resolved.warnings if "no override" not in w]
    assert bool(assumed) == (reason in {"declared_several", "fallback"})


def test_the_deployments_preference_decides_among_several(tmp_path: Path) -> None:
    root = sets(tmp_path, preference=["dublin-core", "datacite-4"])
    resolved = load_requirements(root).resolve(
        ELSEWHERE, "Elsewhere", ["DataCite Metadata Schema", "Dublin Core"]
    )
    assert resolved.standard.requirement_set.requirement_set_id == "dublin-core"
    assert resolved.standard_reason == "declared_several"


@pytest.mark.parametrize("preference", [["datacite-4"], ["datacite-4", "dublin-core", "ddi"]])
def test_a_preference_that_does_not_name_every_set_once_stops_start_up(
    tmp_path: Path, preference: list[str]
) -> None:
    with pytest.raises(RequirementsError, match="every standard's set once"):
        load_requirements(sets(tmp_path, preference=preference))


def test_a_person_may_choose_a_standard_the_deployment_has_a_set_for(tmp_path: Path) -> None:
    requirements = load_requirements(sets(tmp_path))
    resolved = requirements.resolve(ELSEWHERE, "Elsewhere", ["DataCite Metadata Schema"], OAI_DC)
    assert resolved.standard.requirement_set.conforms_to == OAI_DC
    assert resolved.standard_reason == "chosen"
    with pytest.raises(RequirementsError, match="no set for"):
        requirements.resolve(ELSEWHERE, "Elsewhere", [], "https://ddialliance.org/")


def test_a_choice_against_an_overrides_standard_is_refused(tmp_path: Path) -> None:
    requirements = load_requirements(sets(tmp_path, ("overrides", override())))
    assert requirements.resolve(ORDA, "ORDA", [], DATACITE).standard_reason == "override"
    with pytest.raises(RequirementsError, match="written for DataCite"):
        requirements.resolve(ORDA, "ORDA", ["Dublin Core"], OAI_DC)


def test_a_chosen_standard_is_recorded_with_who_chose_it(tmp_path: Path) -> None:
    root = sets(tmp_path)
    projects = ProjectStore(tmp_path / "projects")
    project_id = projects.create(acted_for=TEST_PRINCIPAL, caused_by="test", title="Soil")
    with pytest.raises(ProjectError, match="choose a repository"):
        projects.choose_standard(
            project_id,
            OAI_DC,
            registry=pinned(root / "re3data"),
            requirements=load_requirements(root),
            acted_for=TEST_PRINCIPAL,
            caused_by="test",
        )
    choice: dict[str, Any] = {
        "registry": pinned(root / "re3data"),
        "requirements": load_requirements(root),
        "acted_for": TEST_PRINCIPAL,
        "caused_by": "test",
    }
    projects.choose_repository(project_id, ELSEWHERE, **choice)
    assert projects.requirements(project_id)["conforms_to"] == DATACITE  # type: ignore[index]
    projects.choose_standard(project_id, OAI_DC, **choice)
    # The drafter and validation read the last choice, now in the chosen standard.
    assert projects.requirements(project_id)["conforms_to"] == OAI_DC  # type: ignore[index]
    last = [e for e in projects.events(project_id) if e["event"] == "repository_chosen"][-1]
    assert last["standard"]["reason"] == "chosen"
    assert last["standard"]["ref"].startswith("dublin-core-oai@v")
    assert last["acted_for"]["principal_id"] == TEST_PRINCIPAL.principal_id
    summary = projects.summary(project_id)["repository"]
    assert summary["standard"] == {
        "title": "Dublin Core (OAI-DC)",
        "reason": "chosen",
        "chosen_by": TEST_PRINCIPAL.name,
    }
    # Choosing the repository again goes back to the rule.
    projects.choose_repository(project_id, ELSEWHERE, **choice)
    assert projects.requirements(project_id)["conforms_to"] == DATACITE  # type: ignore[index]
