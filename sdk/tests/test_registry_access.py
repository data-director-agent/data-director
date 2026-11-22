"""dd_sdk.registry: the retrieval types, the tokeniser and FAIRsharing's API."""

from __future__ import annotations

import json

import httpx
import pytest

from dd_sdk.registry import Hit, Query, RegistryUnavailable, SnapshotRef
from dd_sdk.registry.fairsharing import SEARCH, SIGN_IN, FairsharingClient
from dd_sdk.registry.tokenise import STOP_WORDS, fold, tokenise


def test_a_query_describes_its_record_type_only_when_it_has_one() -> None:
    plain = Query("soil", label="topic")
    typed = Query("soil", label="topic", record_type="terminology_artefact")
    assert "soil" in plain.describe()
    assert "terminology_artefact" not in plain.describe()
    assert "terminology_artefact" in typed.describe()


def test_a_stale_snapshot_ref_says_so() -> None:
    assert SnapshotRef("x").as_string() == "x"
    assert SnapshotRef("x", stale=True).as_string() != "x"


def test_a_hit_carries_any_record() -> None:
    hit: Hit[str] = Hit("record", 1.5)
    assert (hit.record, hit.lexical_score) == ("record", 1.5)


def test_stop_words_and_single_letters_are_dropped() -> None:
    assert tokenise("The soil of a field, x") == ["soil", "field"]


def test_an_agent_chooses_its_own_stop_words() -> None:
    assert "data" in tokenise("soil data")
    assert "data" not in tokenise("soil data", STOP_WORDS | {"data"})


@pytest.mark.parametrize(
    ("plural", "singular"),
    [("sciences", "science"), ("studies", "study"), ("glass", "glass"), ("corpus", "corpus")],
)
def test_folding_makes_a_plural_and_its_singular_alike(plural: str, singular: str) -> None:
    assert fold(plural) == fold(singular)
    assert tokenise(plural, fold_plurals=True) == tokenise(singular, fold_plurals=True)


def test_folding_is_off_unless_asked_for() -> None:
    assert tokenise("sciences") == ["sciences"]


def _client(handler: httpx.MockTransport) -> FairsharingClient:
    return FairsharingClient(httpx.Client(transport=handler), login="l", password="p")


def test_search_signs_in_once_and_sends_the_token() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if str(request.url) == SIGN_IN:
            return httpx.Response(200, json={"jwt": "t"})
        return httpx.Response(200, json={"data": [{"id": 1}]})

    client = _client(httpx.MockTransport(handle))
    assert client.search({"q": "soil"}).value == [{"id": 1}]
    assert client.search({"q": "rock"}).value == [{"id": 1}]
    signs_in = [r for r in seen if str(r.url) == SIGN_IN]
    searches = [r for r in seen if str(r.url).startswith(SEARCH)]
    assert len(signs_in) == 1
    assert json.loads(signs_in[0].content) == {"user": {"login": "l", "password": "p"}}
    assert all(r.headers["Authorization"] == "Bearer t" for r in searches)


def test_search_without_an_account_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAIRSHARING_LOGIN", raising=False)
    monkeypatch.delenv("FAIRSHARING_PASSWORD", raising=False)
    client = FairsharingClient(httpx.Client(transport=httpx.MockTransport(lambda r: None)))  # type: ignore[arg-type]
    assert not client.signed_in
    with pytest.raises(RegistryUnavailable):
        client.search({"q": "soil"})


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(500),
        httpx.Response(200, json={"error": "no"}),
    ],
)
def test_a_failed_search_is_unavailable(answer: httpx.Response) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if str(request.url) == SIGN_IN:
            return httpx.Response(200, json={"jwt": "t"})
        return answer

    with pytest.raises(RegistryUnavailable):
        _client(httpx.MockTransport(handle)).search({"q": "soil"})


def test_a_sign_in_without_a_token_is_unavailable() -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    with pytest.raises(RegistryUnavailable):
        client.search({"q": "soil"})


@pytest.mark.parametrize(
    ("answer", "found"),
    [
        (httpx.Response(200, json={"name": "x"}), {"name": "x"}),
        (httpx.Response(404), None),
        (httpx.Response(200, text="<html>", headers={"content-type": "text/html"}), None),
        (httpx.Response(200, json=[1]), None),
    ],
)
def test_get_json_reads_a_record_or_none(answer: httpx.Response, found: object) -> None:
    client = _client(httpx.MockTransport(lambda r: answer))
    assert client.get_json("https://fairsharing.org/FAIRsharing.x").value == found


def test_get_json_on_a_server_error_is_unavailable() -> None:
    client = _client(httpx.MockTransport(lambda r: httpx.Response(503)))
    with pytest.raises(RegistryUnavailable):
        client.get_json("https://fairsharing.org/FAIRsharing.x")
