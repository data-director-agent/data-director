"""Ranking by DFG subject and by BM25 score: `dfg` and `rank` without the agent."""

from __future__ import annotations

import pytest

from dd_agent_advisor_repository import assess, dfg, rank
from dd_agent_advisor_repository.classes import AccessNeed, Affiliation, RepositoryNeeds
from dd_agent_advisor_repository.records import Institution, Re3dataRecord
from dd_agent_advisor_repository.retrieve import Hit, Query
from dd_agent_advisor_repository.snapshot import fold, tokenise

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


# --- the researcher's country (#741) ----------------------------------------------------------

HOME = Affiliation(name="University of Example", ror="https://ror.org/000000000")


def operated_in(rid: str, country: str, *codes: str) -> Re3dataRecord:
    return repository(rid, *codes).model_copy(
        update={"institutions": [Institution(name=f"Trust {country}", country=country)]}
    )


def ranked_ids(needs: RepositoryNeeds, *pairs: tuple[Re3dataRecord, float]) -> list[str]:
    matches = matched(needs, {t: list(pairs) for t in needs.themes})
    return order(needs, matches, *(r for r, _ in pairs))


@pytest.mark.parametrize("country", ["AAA", "BBB"])
def test_a_repository_in_the_researchers_country_ranks_first_among_equals(country: str) -> None:
    """No country is special: whichever is given, its repository goes first."""
    a = operated_in("r3d100000201", "AAA", "3", "34", "346", "34601")
    b = operated_in("r3d100000202", "BBB", "3", "34", "346", "34601")
    needs = HYDROLOGY.model_copy(update={"country": country})
    first = a if country == "AAA" else b
    assert ranked_ids(needs, (a, 5.0), (b, 5.0))[0] == first.re3data_id


def test_the_country_does_not_outweigh_a_clearly_better_match() -> None:
    near = operated_in("r3d100000211", "AAA", "3", "34", "346", "34601")
    far = operated_in("r3d100000212", "BBB", "3", "34")
    needs = HYDROLOGY.model_copy(update={"country": "BBB"})
    assert ranked_ids(needs, (near, 5.0), (far, 5.0)) == [near.re3data_id, far.re3data_id]


def test_the_country_adds_no_repository_on_its_own() -> None:
    off_theme = operated_in("r3d100000221", "AAA", "12", "124")
    needs = HYDROLOGY.model_copy(update={"country": "AAA"})
    ranked = rank.rank(matched(needs, {}), {off_theme.re3data_id: off_theme}, needs)
    assert ranked == []


def test_the_country_lifts_no_repository_over_the_floor() -> None:
    """A repository just below the floor stays below it, whatever its country."""
    floor = rank.config()["confidence_floor"]
    weak = operated_in("r3d100000241", "AAA")
    # One theme of four, by text alone: a quarter of the theme weight, just under the floor.
    needs = RepositoryNeeds(themes=["moorland", "peat", "bog", "heath"], country="AAA")
    matches = matched(needs, {"moorland": [(weak, 1.0)]})
    weights = rank.config()["weights"]
    assert weights["theme"] / 4 < floor <= weights["theme"] / 4 + weights["country"]
    assert rank.rank(matches, {weak.re3data_id: weak}, needs) == []


def test_an_unset_country_is_read_from_the_affiliations_institution() -> None:
    a = operated_in("r3d100000231", "AAA", "3", "34", "346", "34601")
    b = operated_in("r3d100000232", "BBB", "3", "34", "346", "34601")
    home = repository("r3d100000233").model_copy(
        update={"institutions": [Institution(name=HOME.name, country="BBB", ror="000000000")]}
    )
    needs = HYDROLOGY.model_copy(update={"affiliation": HOME})
    matches = matched(needs, {"hydrology": [(a, 5.0), (b, 5.0)]})
    ranked = rank.rank(matches, {r.re3data_id: r for r in (a, b, home)}, needs)
    assert ranked[0].record.re3data_id == b.re3data_id
    assert any("researcher's institution" in r for r in ranked[0].reasons)
    assert assess.home_country([a, b, home], HOME) == "BBB"
    assert assess.home_country([a, b], HOME) is None


def test_records_that_disagree_on_the_institutions_country_give_the_commonest() -> None:
    def home(rid: str, country: str) -> Re3dataRecord:
        return repository(rid).model_copy(
            update={"institutions": [Institution(name=HOME.name, country=country, ror="000000000")]}
        )

    records = [home("r3d1", "BBB"), home("r3d2", "AAA"), home("r3d3", "BBB")]
    assert assess.home_country(records, HOME) == "BBB"
    assert assess.home_country(reversed(records), HOME) == "BBB"
    assert assess.home_country(records[:2], HOME) == "AAA"  # a tie goes to code order


# --- equal ranks ------------------------------------------------------------------------------


def test_only_repositories_of_the_same_fit_and_score_are_said_to_be_ranked_equal() -> None:
    def ranked(rid: str, score: float, fit: str = rank.DISCIPLINE) -> rank.Ranked:
        return rank.Ranked(repository(rid), score, ("reason",), fit)

    out = rank._say_ties(
        [
            ranked("r3d1", 1.1),
            ranked("r3d2", 1.0),
            ranked("r3d3", 1.0),
            ranked("r3d4", 1.0, rank.GENERALIST),
        ]
    )
    assert [len(r.reasons) for r in out] == [1, 2, 2, 1]
    assert out[1].reasons[-1] == out[2].reasons[-1]


# --- plurals ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("plural", "singular"),
    [
        ("sciences", "science"),
        ("studies", "study"),
        ("repositories", "repository"),
        ("models", "model"),
        ("environmental sciences", "environmental science"),
    ],
)
def test_a_plural_and_its_singular_tokenise_alike(plural: str, singular: str) -> None:
    assert tokenise(plural) == tokenise(singular)


@pytest.mark.parametrize("word", ["analysis", "glass", "status", "census", "gas"])
def test_a_word_that_is_not_a_plural_is_left_alone(word: str) -> None:
    assert fold(word) == word
