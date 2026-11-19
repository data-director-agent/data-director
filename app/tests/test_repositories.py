"""The app's repository requirements load, and a choice of ORDA or a NERC EDS centre resolves as
its steward meant (docs/specs/deposit.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from dd_harness.requirements import DATACITE, load_requirements
from dd_sdk.contract.models import RepositoryRequirements

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


def test_eidc_is_checked_against_datacite_and_its_service_agreement() -> None:
    """#1074: re3data lists DataCite, Dublin Core and ISO 19115 for the EIDC; its override names
    DataCite, which its DOIs are registered with, and adds what its Service Agreement requires."""
    resolved = load_requirements(REPOSITORIES).resolve(
        "r3d100010199",
        "NERC EDS Environmental Information Data Centre",
        ["DataCite Metadata Schema", "Dublin Core", "ISO 19115"],
    )
    assert [s.ref.split("@")[0] for s in resolved.sets] == ["datacite-4", "eidc"]
    assert resolved.warnings == ()
    merged = resolved.requirements()
    RepositoryRequirements.model_validate(merged)
    assert merged["conforms_to"] == DATACITE
    required = {
        f.get("form_label", f["property"])
        for f in merged["fields"]
        if f["obligation"] == "required"
    }
    assert {"Title", "Authors", "Description", "Lineage", "End user licence"} <= required
    lineage = next(f for f in merged["fields"] if f.get("form_label") == "Lineage")
    assert lineage["qualifier"] == {"descriptionType": "Methods"}
    assert merged["licences"][0] == "OGL-UK-3.0" and "CC-BY-4.0" in merged["licences"]
    assert "CC0-1.0" not in merged["licences"]
    assert merged["required_documents"] == ["metadata_record", "readme", "data_dictionary"]
    assert merged["repository_url"] == "https://eidc.ac.uk/deposit"


@pytest.mark.parametrize(
    ("re3data_id", "name", "standards", "set_id"),
    [
        ("r3d100010192", "British Oceanographic Data Centre", ["Dublin Core"], "bodc"),
        ("r3d100012305", "Centre for Environmental Data Analysis", ["Dublin Core"], "ceda"),
        ("r3d100010189", "National Geoscience Data Centre", ["ISO 19115"], "ngdc"),
        ("r3d100010120", "UK Polar Data Centre", ["ISO 19115"], "ukpdc"),
    ],
)
def test_the_other_nerc_eds_centres_build_on_datacite(
    re3data_id: str, name: str, standards: list[str], set_id: str
) -> None:
    """#1250: each centre registers its DOIs with DataCite, whatever re3data lists for it, and
    requires a lineage or methods beyond DataCite's abstract, under OGL by default."""
    resolved = load_requirements(REPOSITORIES).resolve(re3data_id, name, standards)
    assert [s.ref.split("@")[0] for s in resolved.sets] == ["datacite-4", set_id]
    assert resolved.warnings == ()
    merged = resolved.requirements()
    RepositoryRequirements.model_validate(merged)
    assert merged["conforms_to"] == DATACITE
    abstract = next(
        f for f in merged["fields"] if f.get("qualifier") == {"descriptionType": "Abstract"}
    )
    assert abstract["obligation"] == "required"
    assert any(f.get("qualifier") == {"descriptionType": "Methods"} for f in merged["fields"])
    assert merged["licences"][0] == "OGL-UK-3.0"
    assert {"metadata_record", "readme"} <= set(merged["required_documents"])
    assert merged["unconfirmed"]


def test_any_other_repository_is_checked_against_its_standard_with_a_warning() -> None:
    resolved = load_requirements(REPOSITORIES).resolve(
        "r3d100010468", "Zenodo", ["DataCite Metadata Schema", "Dublin Core"]
    )
    assert [s.ref.split("@")[0] for s in resolved.sets] == ["datacite-4"]
    (warning,) = resolved.warnings
    assert "no override for Zenodo" in warning
