"""Estimated energy and cost of an invocation's model calls (Blueprint P14 and C17;
docs/specs/disclosure.md, Footprint).

The profile's `model_footprint` gives, for each model the deployment calls, a price per million
input and output tokens and an energy factor in joules per input and output token, with the
source of those figures and the date they were taken. An estimate is tokens times factor: a
modelled figure, never a measurement, and only as good as the factors the steward wrote.

A call is estimated only if its model is in the table and the provider reported both its token
counts. A run's total is the sum over its calls, and exists only if every call has a figure: a
partial sum would read as the whole. A run that called no model has no estimate, because nothing
was modelled; its own compute, the harness's and the network's are not estimated at all. A
delegating run's figure covers its own calls, not its children's, each of which has its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

_TABLE_KEYS = frozenset({"source", "as_of", "currency", "models"})
_RATE_KEYS = frozenset(
    {"input_per_mtok", "output_per_mtok", "input_j_per_token", "output_j_per_token"}
)
_PER_MTOK = 1_000_000


@dataclass(frozen=True)
class ModelRate:
    """One model's figures. A price or an energy factor left out is not zero: calls to the model
    then have no cost, or no energy, estimate."""

    input_per_mtok: float | None = None
    output_per_mtok: float | None = None
    input_j_per_token: float | None = None
    output_j_per_token: float | None = None


@dataclass(frozen=True)
class FootprintTable:
    """The profile's `model_footprint`: the figures every estimate in a run is made from."""

    source: str
    as_of: date
    currency: str | None = None
    models: Mapping[str, ModelRate] = field(default_factory=dict)

    @property
    def basis(self) -> str:
        """What a reader is told the estimates rest on."""
        return f"{self.source} (as of {self.as_of.isoformat()})"

    @classmethod
    def from_value(cls, value: Any) -> FootprintTable | None:
        """Read the profile's `model_footprint`; None when the profile has none. Raises
        `TypeError` or `ValueError` on a malformed table, which the profile loader reports."""
        if value is None:
            return None
        if not isinstance(value, dict):
            raise TypeError("model_footprint must be a mapping with source, as_of and models")
        if unknown := sorted(set(value) - _TABLE_KEYS):
            raise ValueError(f"model_footprint has keys nothing reads: {', '.join(unknown)}")
        source, as_of = value.get("source"), value.get("as_of")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("model_footprint must name the source of its figures")
        if not isinstance(as_of, date):
            raise TypeError("model_footprint's as_of must be a date, written YYYY-MM-DD")
        currency = value.get("currency")
        if currency is not None and (
            not isinstance(currency, str) or len(currency) != 3 or not currency.isupper()
        ):
            raise ValueError("model_footprint's currency must be an ISO 4217 code, such as GBP")
        models = value.get("models") or {}
        if not isinstance(models, dict):
            raise TypeError("model_footprint's models must map each model ID to its figures")
        rates = {str(m): _rate(str(m), r) for m, r in models.items()}
        if currency is None and any(
            r.input_per_mtok is not None or r.output_per_mtok is not None for r in rates.values()
        ):
            raise ValueError("model_footprint gives prices, so it must name their currency")
        return cls(source.strip(), as_of, currency, rates)


def _rate(model: str, written: Any) -> ModelRate:
    if not isinstance(written, dict):
        raise TypeError(f"model_footprint model {model} must map each figure to a number")
    if unknown := sorted(set(written) - _RATE_KEYS):
        raise ValueError(f"model_footprint model {model} has keys nothing reads: {unknown}")
    figures: dict[str, float] = {}
    for key, number in written.items():
        if isinstance(number, bool) or not isinstance(number, int | float) or number < 0:
            raise ValueError(f"model_footprint {model}.{key} must be a number of at least 0")
        figures[str(key)] = float(number)
    return ModelRate(**figures)


@dataclass(frozen=True)
class Estimate:
    """The estimated energy in joules and cost in the table's currency of one call or one run;
    None where it cannot be estimated."""

    energy_j: float | None = None
    cost: float | None = None


def _times(tokens_in: int, tokens_out: int, per_in: float | None, per_out: float | None) -> float:
    assert per_in is not None and per_out is not None
    return tokens_in * per_in + tokens_out * per_out


def estimate_call(
    table: FootprintTable | None,
    model_id: str,
    input_tokens: int | None,
    output_tokens: int | None,
) -> Estimate:
    """One call's estimate, from the model the provider named and the tokens it reported."""
    rate = table.models.get(model_id) if table is not None else None
    if rate is None or input_tokens is None or output_tokens is None:
        return Estimate()
    energy = (
        _times(input_tokens, output_tokens, rate.input_j_per_token, rate.output_j_per_token)
        if rate.input_j_per_token is not None and rate.output_j_per_token is not None
        else None
    )
    cost = (
        _times(input_tokens, output_tokens, rate.input_per_mtok, rate.output_per_mtok) / _PER_MTOK
        if rate.input_per_mtok is not None and rate.output_per_mtok is not None
        else None
    )
    return Estimate(energy, cost)


def total(calls: Iterable[Estimate]) -> Estimate:
    """A run's estimate: the sum over its calls, each figure only if every call has it."""
    estimates = list(calls)
    if not estimates:
        return Estimate()
    energies = [e.energy_j for e in estimates]
    costs = [e.cost for e in estimates]
    return Estimate(
        None if None in energies else sum(e for e in energies if e is not None),
        None if None in costs else sum(c for c in costs if c is not None),
    )


def estimate_calls(
    table: FootprintTable | None, calls: Iterable[Mapping[str, Any]]
) -> list[Estimate]:
    """Each call's estimate, from the calls as an envelope document lists them."""
    return [
        estimate_call(table, c["model_id"], c.get("input_tokens"), c.get("output_tokens"))
        for c in calls
    ]
