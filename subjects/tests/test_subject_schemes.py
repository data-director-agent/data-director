"""Each scheme loads whole, with its provenance, and suggests its fields broad first."""

import pytest

from dd_subjects import SCHEMES, scheme, suggestions


@pytest.mark.parametrize("scheme_id", SCHEMES)
def test_a_scheme_says_where_it_comes_from(scheme_id: str) -> None:
    s = scheme(scheme_id)
    assert s.id == scheme_id
    assert all([s.name, s.version, s.source, s.licence, s.attribution])


@pytest.mark.parametrize("scheme_id", SCHEMES)
def test_every_code_is_unique_and_every_parent_is_a_top_level_field(scheme_id: str) -> None:
    terms = scheme(scheme_id).terms
    codes = [t.code for t in terms]
    assert len(set(codes)) == len(codes)
    top = {t.code for t in terms if t.parent is None}
    assert top
    assert all(t.parent in top for t in terms if t.parent is not None)
    assert all(t.label.strip() == t.label and t.label for t in terms)


@pytest.mark.parametrize("scheme_id", SCHEMES)
def test_suggestions_put_each_broad_field_before_the_fields_under_it(scheme_id: str) -> None:
    terms = scheme(scheme_id).terms
    offered = suggestions(scheme_id)
    assert len(set(offered)) == len(offered)
    position = {label: i for i, label in enumerate(offered)}
    labels = {t.code: t.label for t in terms}
    for t in terms:
        if t.parent is not None:
            assert position[labels[t.parent]] < position[t.label]


def test_an_unknown_scheme_is_refused() -> None:
    with pytest.raises(KeyError):
        scheme("no-such-scheme")
