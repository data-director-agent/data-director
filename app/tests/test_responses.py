"""Response models (#1130): a route answers through its model, a fixture is checked against it,
and every model the app declares is gathered into one JSON Schema."""

from __future__ import annotations

import json
from typing import Any, Literal

import pytest
from pydantic import MISSING, ValidationError
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route
from starlette.testclient import TestClient
from support import conforms

from dd_app.problems import ProblemDetails, problem
from dd_app.responses import (
    ResponseBody,
    main,
    respond,
    respond_page,
    response_models,
    response_schema,
)
from dd_harness.listing import Page


class Item(ResponseBody):
    """A test's own model, which `response_models` leaves out."""

    name: str
    note: str | None
    size: int | MISSING = MISSING


class Measured(ResponseBody):
    weight: float
    state: Literal["proposed", "approved"] | MISSING = MISSING


def test_a_response_is_what_its_model_describes() -> None:
    sent = respond(Item, {"name": "a", "note": None}, status_code=201, headers={"X-A": "1"})
    assert sent.status_code == 201
    assert sent.headers["x-a"] == "1"
    # Null is kept, and a field left out stays out.
    assert json.loads(bytes(sent.body)) == {"name": "a", "note": None}
    assert json.loads(bytes(respond(Item, Item(name="a", note="b", size=3)).body))["size"] == 3


@pytest.mark.parametrize(
    "body",
    [
        {"name": "a", "note": None, "colour": "red"},  # a key the model does not name
        {"name": "a"},  # a key it requires
        {"name": 1, "note": None},  # a value of another type, not coerced
        {"name": "a", "note": None, "size": None},  # null where the key may only be left out
    ],
)
def test_a_body_the_model_does_not_describe_is_an_error(body: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        respond(Item, body)


def test_a_page_answers_each_item_through_its_model() -> None:
    async def listing(request: Request) -> Response:
        return respond_page(request, Page(items=[{"name": "a", "note": None}], next="c"), Item)

    client = TestClient(Starlette(routes=[Route("/items", listing)]))
    answered = client.get("/items?limit=1")
    assert answered.json() == [{"name": "a", "note": None}]
    assert 'rel="next"' in answered.headers["link"]


def test_a_problem_keeps_its_extension_members() -> None:
    sent = problem(409, "package-refused", "No package", "Not yet.", validation={"ok": False})
    assert sent.headers["content-type"] == "application/problem+json"
    body = json.loads(bytes(sent.body))
    assert body["validation"] == {"ok": False}
    conforms(body, ProblemDetails)


def test_a_fixture_must_be_what_its_model_describes() -> None:
    conforms([{"name": "a", "note": None}], list[Item])
    with pytest.raises(AssertionError, match="does not fit"):
        conforms({"name": "a", "note": None, "colour": "red"}, Item)
    # Read as a float, a whole number would go out as `1.0`: the model must give back what it read.
    with pytest.raises(AssertionError, match="does not give back"):
        conforms({"weight": 1}, Measured)
    conforms({"weight": 1.5, "state": "approved"}, Measured)
    with pytest.raises(AssertionError, match="does not fit"):
        conforms({"weight": 1.5, "state": "rejected"}, Measured)


def test_every_model_the_app_declares_is_found() -> None:
    models = response_models()
    assert ProblemDetails in models
    assert Item not in models
    assert len({m.__name__ for m in models}) == len(models)


@pytest.mark.parametrize("model", response_models(), ids=lambda m: m.__name__)
def test_a_field_is_either_always_sent_or_left_out_when_missing(
    model: type[ResponseBody],
) -> None:
    """Any other default would describe a key the handler did not send."""
    for name, field in model.model_fields.items():
        assert field.is_required() or field.default is MISSING, f"{model.__name__}.{name}"


def test_the_schema_holds_every_model_and_only_models() -> None:
    schema = response_schema()
    defined = schema["$defs"]
    names = {m.__name__ for m in response_models()}
    assert names <= defined.keys()
    # A nested model is a `ResponseBody` too, so it is named and closed alike; a closed set of
    # values is a `Literal`, not an `Enum`, which a strict model would not read from JSON.
    assert defined.keys() <= names
    for definition in defined.values():
        for field in definition.get("properties", {}).values():
            assert "title" not in field


def test_the_schema_can_be_printed(capsys: pytest.CaptureFixture[str]) -> None:
    main()
    assert json.loads(capsys.readouterr().out) == response_schema()
