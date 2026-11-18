"""The bodies the app's routes answer with, as Pydantic models (#1130).

Each route module declares a `ResponseBody` for each JSON body it sends, beside its handlers, and
answers through `respond` (or `respond_page` for a listing), so what goes out is what the model
says. The models describe exactly what the server sends: a field that is always there has no
default (`T`, or `T | None` when it may be null); a field that is sometimes left out defaults to
`MISSING` (`T | MISSING = MISSING`) and is then omitted, never sent as null. No other default is
allowed, as one would add a key the handler did not send. The tests check each golden fixture
against its model (`check_fixture(..., model=...)` in `app/tests/support.py`).

`response_schema` gathers every `ResponseBody` the app defines into one JSON Schema, from which
the shell's TypeScript types are to be generated; `python -m dd_app.responses` prints it.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from functools import cache
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic.json_schema import GenerateJsonSchema, JsonSchemaValue, models_json_schema
from pydantic_core import CoreSchema
from starlette.requests import Request
from starlette.responses import JSONResponse

from dd_harness.listing import Page
from dd_harness.transport.paging import page_response


class ResponseBody(BaseModel):
    """A JSON body a route sends. Its class name becomes the TypeScript interface's name, and its
    docstring and field docstrings the interface's comments.

    Strict, so a value of the wrong type is an error rather than coerced into another, and closed,
    so a key the model does not name is an error rather than sent undescribed.
    """

    model_config = ConfigDict(
        strict=True, extra="forbid", frozen=True, use_attribute_docstrings=True
    )


@cache
def adapter(model: Any) -> TypeAdapter[Any]:
    """A validator for `model`: a `ResponseBody`, or a type built of them such as `list[...]`."""
    return TypeAdapter(model)


def dump(model: Any, body: object) -> Any:
    """`body` (a model, or the dicts and lists the handler built) checked against `model` and
    turned into JSON values. Raises `pydantic.ValidationError` if it does not fit: a programmer's
    error, as the handler sent what its model does not describe."""
    checked = adapter(model)
    return checked.dump_python(checked.validate_python(body), mode="json")


def respond(
    model: Any,
    body: object,
    *,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
    media_type: str | None = None,
) -> JSONResponse:
    """A JSON response whose body is `body` as `model` describes it."""
    return JSONResponse(
        dump(model, body), status_code=status_code, headers=headers, media_type=media_type
    )


def respond_page(request: Request, page: Page, item: type[ResponseBody]) -> JSONResponse:
    """A page of a listing (`dd_harness.transport.paging`), each item as `item` describes it."""
    items = dump(list[item], page.items)  # type: ignore[valid-type]  # a type built at run time
    return page_response(request, dataclasses.replace(page, items=items))


def response_models() -> list[type[ResponseBody]]:
    """Every `ResponseBody` the app defines, by name. Found by importing the app, which imports
    every route module, so a model is registered by being declared, not by being listed."""
    import dd_app.app  # noqa: F401  (imported for its models)

    found: dict[str, type[ResponseBody]] = {}
    pending = list(ResponseBody.__subclasses__())
    while pending:
        model = pending.pop()
        pending += model.__subclasses__()
        if not model.__module__.startswith("dd_app."):
            continue  # a test's own
        if (other := found.setdefault(model.__name__, model)) is not model:
            raise TypeError(
                f"Two response models are named {model.__name__!r}: "
                f"{other.__module__} and {model.__module__}; the TypeScript names would clash."
            )
    return [found[name] for name in sorted(found)]


class _Untitled(GenerateJsonSchema):
    """No title on each field: json-schema-to-typescript would make each a named type."""

    def field_title_should_be_set(self, schema: CoreSchema) -> bool:
        return False


def response_schema() -> JsonSchemaValue:
    """One JSON Schema whose `$defs` hold every response model, as it is sent."""
    _, schema = models_json_schema(
        [(model, "serialization") for model in response_models()],
        title="Data Director app responses",
        schema_generator=_Untitled,
    )
    return schema


def main() -> None:
    sys.stdout.write(json.dumps(response_schema(), indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
