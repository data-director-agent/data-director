"""Deployment roles from the profile (docs/specs/stewardship.md, invariant 1; #154).

The profile's `stewardship` key names the steward teams and its `administrators` key the
administrators. Everyone is a researcher; nobody is a steward or an administrator by signing in.
"""

from __future__ import annotations

from typing import Any

import pytest
import yaml

from dd_harness.policy import PolicyError, Profile
from dd_harness.stewardship import DeploymentRole
from dd_harness.testing import PERMISSIVE

ADA = "https://orcid.org/0000-0001-5000-0007"
JOSIAH = "https://orcid.org/0000-0002-1825-0097"
GRACE = "https://orcid.org/0000-0002-1694-233X"

TEAM = {
    "id": "library-rdm",
    "name": "Library Research Data Team",
    "members": [ADA, GRACE],
    "supports": ["faculty-of-science"],
    "contact": "https://example.ac.uk/rdm",
    "response_time": "3 working days",
}


def profile(**keys: Any) -> Profile:
    data = yaml.safe_load(PERMISSIVE.read_text())
    data.update(keys)
    return Profile.from_mapping(data, source="test", digest="0" * 64)


def test_a_profile_without_the_keys_has_no_stewards_and_no_administrators() -> None:
    found = profile()
    assert found.stewardship.teams == ()
    assert found.administrators == frozenset()
    roles = found.roles_of(JOSIAH)
    assert roles.roles == {DeploymentRole.RESEARCHER}
    assert roles.teams == ()


def test_the_profile_names_each_team_and_its_members() -> None:
    found = profile(stewardship={"teams": [TEAM]})
    (team,) = found.stewardship.teams
    assert team.team_id == "library-rdm"
    assert team.members == {ADA, GRACE}
    assert team.supports == ("faculty-of-science",)
    assert team.contact == "https://example.ac.uk/rdm"
    assert team.response_time == "3 working days"
    assert found.stewardship.visibility == "escalated"
    assert found.stewardship.deposit_co_approval is False
    assert found.stewardship.team("library-rdm") == team
    assert found.stewardship.team("elsewhere") is None


def test_a_person_a_team_lists_is_a_steward_of_that_team_and_still_a_researcher() -> None:
    found = profile(stewardship={"teams": [TEAM, {**TEAM, "id": "faculty", "members": [ADA]}]})
    roles = found.roles_of(ADA)
    assert roles.roles == {DeploymentRole.RESEARCHER, DeploymentRole.STEWARD}
    assert [t.team_id for t in roles.teams] == ["library-rdm", "faculty"]
    assert found.roles_of(GRACE).steward
    assert not found.roles_of(JOSIAH).steward


def test_an_administrator_is_named_by_administrators_alone() -> None:
    found = profile(administrators=[JOSIAH], stewardship={"teams": [TEAM]})
    assert found.roles_of(JOSIAH).roles == {
        DeploymentRole.RESEARCHER,
        DeploymentRole.ADMINISTRATOR,
    }
    assert found.roles_of(JOSIAH).administrator
    assert not found.roles_of(ADA).administrator


def test_a_bare_orcid_id_is_refused_because_it_names_no_principal() -> None:
    with pytest.raises(PolicyError, match=r"https://orcid\.org/0000-0002-1825-0097"):
        profile(administrators=["0000-0002-1825-0097"])
    with pytest.raises(PolicyError, match="bare ORCID iD"):
        profile(stewardship={"teams": [{**TEAM, "members": ["0000-0001-5000-0007"]}]})


@pytest.mark.parametrize(
    "stewardship",
    [
        "library-rdm",
        {"teams": "library-rdm"},
        {"teams": [{**TEAM, "id": "Library RDM"}]},
        {"teams": [{**TEAM, "name": ""}]},
        {"teams": [{**TEAM, "members": []}]},
        {"teams": [{**TEAM, "members": [ADA, 7]}]},
        {"teams": [{**TEAM, "supports": "faculty-of-science"}]},
        {"teams": [{**TEAM, "contact": 3}]},
        {"teams": [{**TEAM, "escalate_to": "the dean"}]},
        {"teams": [TEAM, TEAM]},
        {"teams": [TEAM], "visibility": "everything"},
        {"teams": [TEAM], "deposit_co_approval": "yes"},
        {"teams": [TEAM], "reviews": {}},
    ],
)
def test_a_malformed_stewardship_key_stops_start_up(stewardship: Any) -> None:
    with pytest.raises(PolicyError, match="stewardship"):
        profile(stewardship=stewardship)


@pytest.mark.parametrize(
    "stewardship",
    [
        {"teams": [TEAM], "visibility": "scope"},
        {"teams": [TEAM], "deposit_co_approval": True},
    ],
)
def test_a_choice_nothing_enforces_yet_is_refused(stewardship: Any) -> None:
    # A steward cannot yet open a project, nor a deposit wait for a co-approval: a profile that
    # promised either would tell a steward a rule is in force when it is not.
    with pytest.raises(PolicyError, match="not enforced yet"):
        profile(stewardship=stewardship)


@pytest.mark.parametrize("administrators", ["https://orcid.org/0000-0002-1825-0097", [""], [3]])
def test_malformed_administrators_stop_start_up(administrators: Any) -> None:
    with pytest.raises(PolicyError, match="administrators"):
        profile(administrators=administrators)
