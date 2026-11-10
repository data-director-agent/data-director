"""Ranking by DFG subject and by BM25 score: `dfg` and `rank` without the agent."""

from __future__ import annotations

from dd_agent_advisor_repository import dfg, rank
from dd_agent_advisor_repository.classes import AccessNeed, RepositoryNeeds
from dd_agent_advisor_repository.records import Institution, Re3dataRecord
from dd_agent_advisor_repository.retrieve import Hit, Query

NAMES = {
    "2": "Life Sciences",
    "22": "Medicine",
    "222": "Medicine",
    "22220": "Pediatric and Adolescent Medicine",
    "23": "Agriculture, Forestry and Veterinary Medicine",
    "231": "Agriculture, Forestry and Veterinary Medicine",
    "23101": "Soil Sciences",
    "23108": "Veterinary Medical Science",
    "3": "Natural Sciences",
    "32": "Physics",
    "322": "Statistical Physics, Nonlinear Dynamics, Complex Systems, Soft and Fluid Matter",
    "34": "Geosciences",
    "346": "Water Research",
    "34601": "Hydrogeology, Hydrology, Limnology, Urban Water Management",
    "12": "Social and Behavioural Sciences",
    "124": "Economics",
    "12407": "Economic and Social History",
}


def coded(*codes: str) -> list[str]:
    return [f"{c} {NAMES[c]}" for c in codes]


def repository(rid: str, *codes: str) -> Re3dataRecord:
    return Re3dataRecord(
        re3data_id=rid,
        name=f"Repository {rid}",
        subjects=coded(*codes),
        institutions=[Institution(name="Data Trust", type="non-profit")],
        data_access_types=["open"],
        data_upload_types=["restricted"],
    )


# --- dfg ------------------------------------------------------------------------------------


def test_a_subject_is_parsed_from_its_code_and_one_without_a_code_is_not() -> None:
    assert dfg.parse("34601 Hydrology") == ("34601", "Hydrology")
    assert dfg.parse("Social Sciences") is None
    assert dfg.codes(["34 Geosciences", "Social Sciences"]) == {"34"}


def test_a_codes_parents_are_its_prefixes_nearest_first() -> None:
    assert dfg.ancestors("34601") == ["346", "34", "3"]
    assert dfg.ancestors("3") == []


def test_a_theme_names_the_closest_subjects_by_whole_field() -> None:
    assert dfg.resolve("hydrology", NAMES) == ["34601"]
    assert dfg.resolve("soil science", NAMES) == ["23101"]  # "Sciences" is the plural
    assert dfg.resolve("medicine", NAMES) == ["22", "222"]  # not veterinary medicine
    assert dfg.resolve("economics", NAMES) == ["124"]  # not "Economic and Social History"
    # Its words are in one subject's name, but in different fields of it.
    assert dfg.resolve("fluid dynamics", NAMES) == []
    assert dfg.resolve("moorland", NAMES) == []


def test_the_nearest_subject_is_the_theme_s_own_then_the_closest_above_never_the_top() -> None:
    assert dfg.nearest(["34601"], {"3", "34", "346", "34601"}) == dfg.SubjectMatch(
        "34601", "34601", 0
    )
    assert dfg.nearest(["34601"], {"3", "34", "346"}) == dfg.SubjectMatch("34601", "346", 1)
    assert dfg.nearest(["34601"], {"3", "34"}) == dfg.SubjectMatch("34601", "34", 2)
    assert dfg.nearest(["34601"], {"3"}) is None
    # Filed only below the theme's subject is filed under it.
    assert dfg.nearest(["222"], {"22220"}) == dfg.SubjectMatch("222", "222", 0)


# --- rank -----------------------------------------------------------------------------------


def matched(
    needs: RepositoryNeeds, hits: dict[str, list[tuple[Re3dataRecord, float]]]
) -> rank.Matches:
    """Matches as the agent builds them, from each query's text hits."""
    matches = rank.Matches()
    themes = [q.text for q in rank.queries(needs) if q.label == rank.THEME]
    rank.resolve(themes, NAMES, matches)
    for query in rank.queries(needs):
        found = [Hit(record=r, lexical_score=s) for r, s in hits.get(query.text, [])]
        matches.add(query, found)
    return matches


def order(needs: RepositoryNeeds, matches: rank.Matches, *records: Re3dataRecord) -> list[str]:
    return [
        r.record.re3data_id for r in rank.rank(matches, {r.re3data_id: r for r in records}, needs)
    ]


HYDROLOGY = RepositoryNeeds(themes=["hydrology"], access=AccessNeed.OPEN)


def test_a_repository_filed_under_the_themes_subject_ranks_above_a_text_match_alone() -> None:
    filed = repository("r3d100000101", "3", "34", "346", "34601")
    physics = repository("r3d100000102", "3", "32")
    # The physics repository is the better text match, but is filed elsewhere.
    matches = matched(HYDROLOGY, {"hydrology": [(physics, 9.0), (filed, 3.0)]})
    assert order(HYDROLOGY, matches, physics, filed) == [filed.re3data_id, physics.re3data_id]


def test_a_repository_filed_nearer_the_themes_subject_ranks_higher() -> None:
    own = repository("r3d100000111", "3", "34", "346", "34601")
    parent = repository("r3d100000112", "3", "34", "346")
    grandparent = repository("r3d100000113", "3", "34")
    hits = [(r, 5.0) for r in (grandparent, parent, own)]
    matches = matched(HYDROLOGY, {"hydrology": hits})
    assert order(HYDROLOGY, matches, grandparent, parent, own) == [
        own.re3data_id,
        parent.re3data_id,
        grandparent.re3data_id,
    ]


def test_a_better_text_match_ranks_higher_when_the_subjects_are_equal() -> None:
    weak = repository("r3d100000121", "3", "34", "346", "34601")
    strong = repository("r3d100000122", "3", "34", "346", "34601")
    matches = matched(HYDROLOGY, {"hydrology": [(strong, 8.0), (weak, 2.0)]})
    ranked = rank.rank(matches, {weak.re3data_id: weak, strong.re3data_id: strong}, HYDROLOGY)
    assert [r.record.re3data_id for r in ranked] == [strong.re3data_id, weak.re3data_id]
    assert ranked[0].score > ranked[1].score


def test_a_repository_filed_under_the_subject_is_recommended_without_a_text_match() -> None:
    filed = repository("r3d100000131", "3", "34", "346", "34601")
    ranked = rank.rank(matched(HYDROLOGY, {}), {filed.re3data_id: filed}, HYDROLOGY)
    assert [r.record.re3data_id for r in ranked] == [filed.re3data_id]
    assert ranked[0].on_theme


def test_a_theme_that_names_no_subject_is_graded_on_its_text_alone() -> None:
    """A rule whose input is missing does not count against a repository: a theme that names no
    DFG subject, or a record that lists none, is judged as before, on its text."""
    needs = RepositoryNeeds(themes=["moorland"], access=AccessNeed.OPEN)
    filed = repository("r3d100000141", "3", "32")
    uncoded = repository("r3d100000142").model_copy(update={"subjects": ["Ecology"]})
    matches = matched(needs, {"moorland": [(filed, 4.0), (uncoded, 4.0)]})
    ranked = rank.rank(matches, {r.re3data_id: r for r in (filed, uncoded)}, needs)
    assert {r.score for r in ranked} == {1.0}


def test_subject_retrieval_prefers_text_matches_then_the_most_specialised() -> None:
    broad = repository("r3d100000151", "2", "3", "34", "346", "34601", "32", "322")
    narrow = repository("r3d100000152", "3", "34", "346", "34601")
    texted = repository("r3d100000153", "2", "3", "34", "346", "34601", "32", "322", "22")
    matches = matched(HYDROLOGY, {"hydrology": [(texted, 1.0)]})
    picked = rank.by_subject("hydrology", [broad, narrow, texted, narrow], matches)
    assert [r.re3data_id for r in picked] == [
        texted.re3data_id,
        narrow.re3data_id,
        broad.re3data_id,
    ]


def test_a_query_asks_for_more_text_hits_than_it_retrieves() -> None:
    [query] = rank.queries(HYDROLOGY)
    assert query == Query(text="hydrology", limit=rank.config()["text_hits"], label=rank.THEME)
    assert rank.config()["text_hits"] >= rank.config()["search_limit"]
