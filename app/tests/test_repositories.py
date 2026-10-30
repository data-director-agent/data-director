"""The app's repository requirements load, and a choice of ORDA resolves as its steward meant
(ADR-0038)."""

from __future__ import annotations

from pathlib import Path

from dd_harness.requirements import DATACITE, load_requirements

REPOSITORIES = Path(__file__).resolve().parents[1] / "config/repositories"


def test_orda_is_checked_against_datacite_and_its_own_form() -> None:
    # re3data lists only Dublin Core for ORDA; its override names DataCite.
    resolved = load_requirements(REPOSITORIES).resolve("r3d100012124", "ORDA", ["Dublin Core"])
    assert [s.ref.split("@")[0] for s in resolved.sets] == ["datacite-4", "orda"]
    assert resolved.warnings == ()
    merged = resolved.requirements()
    assert merged["conforms_to"] == DATACITE
    required = {
        f.get("form_label", f["property"])
        for f in merged["fields"]
        if f["obligation"] == "required"
    }
    assert {"Title", "Authors", "Item type", "Categories", "Keywords", "Description"} <= required
    assert "License" in required
    assert "CC-BY-4.0" in merged["licences"]
    assert merged["recommended_documents"] == ["readme", "data_dictionary"]


def test_any_other_repository_is_checked_against_its_standard_with_a_warning() -> None:
    resolved = load_requirements(REPOSITORIES).resolve(
        "r3d100010468", "Zenodo", ["DataCite Metadata Schema", "Dublin Core"]
    )
    assert [s.ref.split("@")[0] for s in resolved.sets] == ["datacite-4"]
    (warning,) = resolved.warnings
    assert "no override for Zenodo" in warning
