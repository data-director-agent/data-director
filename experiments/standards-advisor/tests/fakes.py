"""Test doubles.

`FakeRegistry` is the reason `RegistryClient` is a `Protocol` rather than an ABC: it satisfies
the interface without importing or subclassing production code, so a change that breaks the
contract shows up as a type error here rather than as a passing test against a base class that
quietly did the work.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from standards_advisor.errors import RegistryUnavailable
from standards_advisor.models.candidates import RegistryQuery
from standards_advisor.models.common import RegistrySnapshotRef, TermList
from standards_advisor.registry.base import (
    RegistryRecord,
    RegistrySearchResult,
    RegistryTerm,
)


class FakeRegistry:
    """A registry stocked with records we wrote, for exercising the later stages.

    The records are invented, so they prove the *pipeline*, never the quality of a
    recommendation. That is the same reason the §5.3 rule bodies are not written yet: a rule
    tested only against a fixture we authored proves the fixture.
    """

    name = "fake"

    def __init__(
        self,
        records: dict[str, list[RegistryRecord]] | None = None,
        *,
        terms: dict[TermList, list[RegistryTerm]] | None = None,
        unavailable_kinds: frozenset[str] = frozenset(),
    ) -> None:
        self.records = records or {}
        self.terms = terms or {}
        self.unavailable_kinds = unavailable_kinds
        self.searches: list[RegistryQuery] = []

    def snapshot(self) -> RegistrySnapshotRef:
        return RegistrySnapshotRef(
            version="2026-09-01",
            source="fake",
            stale=False,
            retrieved_at="2026-09-01T00:00:00+00:00",
        )

    def list_terms(self, list_name: TermList) -> Sequence[RegistryTerm]:
        if list_name not in self.terms:
            raise RegistryUnavailable(f"fake registry has no {list_name} list")
        return self.terms[list_name]

    def search(self, query: RegistryQuery) -> RegistrySearchResult:
        self.searches.append(query)
        if query.kind.value in self.unavailable_kinds:
            raise RegistryUnavailable(f"fake registry cannot search for {query.kind}")
        return RegistrySearchResult(
            query=query,
            snapshot=self.snapshot(),
            records=list(self.records.get(query.kind.value, [])),
        )

    def fetch_record(self, registry_id: str) -> RegistryRecord | None:
        for records in self.records.values():
            for record in records:
                if record.registry_id == registry_id:
                    return record
        return None


def make_record(
    registry_id: str,
    name: str,
    *,
    subtype: str | None = None,
    status: str = "ready",
    fields: dict[str, str] | None = None,
    populated: frozenset[str] | None = None,
) -> RegistryRecord:
    """A record with `populated_fields` derived from what was actually supplied.

    Defaulting `populated_fields` to the keys of `fields` keeps the fixtures honest: a test
    cannot accidentally cite a field the fake never provided, which is exactly the condition
    the §5.5 evidence check exists to catch.
    """
    supplied = fields or {}
    return RegistryRecord(
        registry_id=registry_id,
        name=name,
        doi=f"10.25504/{registry_id}",
        url=f"https://fairsharing.org/{registry_id}",
        record_type="terminology_artefact",
        record_subtype=subtype,
        status=status,
        subjects=["Environmental Science"],
        domains=["soil"],
        fields=supplied,
        populated_fields=populated if populated is not None else frozenset(supplied),
    )


class StructuredFakeChatModel(GenericFakeChatModel):
    """A fake chat model that supports `with_structured_output`.

    `GenericFakeChatModel` does not: the base `with_structured_output` needs `bind_tools`, and
    the fake has no tools, so it raises `NotImplementedError`. This override returns a runnable
    that parses the scripted message content as JSON against the schema.

    It reproduces the `include_raw=True` contract — a mapping with `raw`, `parsed` and
    `parsing_error` — because that shape is exactly what `llm.structured.call_structured`
    handles, and mimicking it is what makes these tests exercise our parse-failure path rather
    than a shortcut. What it does *not* reproduce is any provider's tool-calling mechanics;
    that is the provider's business, not ours.
    """

    def with_structured_output(
        self,
        schema: Any,
        *,
        include_raw: bool = False,
        **kwargs: Any,
    ) -> Any:
        from langchain_core.runnables import RunnableLambda

        def _invoke(messages: Any, config: Any = None) -> Any:
            raw = self.invoke(messages, config=config)
            text = raw.text if isinstance(raw.text, str) else str(raw.content)
            try:
                parsed = schema.model_validate_json(text)
            except Exception as exc:
                if include_raw:
                    return {"raw": raw, "parsed": None, "parsing_error": exc}
                raise
            if include_raw:
                return {"raw": raw, "parsed": parsed, "parsing_error": None}
            return parsed

        return RunnableLambda(_invoke)


def scripted_model(payloads: list[dict[str, Any]] | list[str]) -> StructuredFakeChatModel:
    """A chat model that returns the given payloads in order.

    A `dict` is serialised to JSON; a `str` is returned verbatim, which is how the
    malformed-response test scripts something that will not parse.
    """
    messages = [
        AIMessage(content=item if isinstance(item, str) else json.dumps(item)) for item in payloads
    ]
    return StructuredFakeChatModel(messages=iter(messages))
