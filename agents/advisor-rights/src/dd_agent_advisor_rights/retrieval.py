"""Where the licences come from: the SPDX licence list through the tool gateway, or the packaged
table (docs/specs/agents.md, Tools; #877).

The deterministic shell builds the candidate licences, retrieves each through the gateway
(`ctx.tools.call("spdx", "get_licence", ...)`) before any model is called, and hands the
interpreter a closed set: the table's rows for the licences the gateway returned. A licence it did
not return is left out and named in `limitations`; a call that fails is the same, never an
exception. The payload cites the records the conductor recorded (`dd_sdk.tools.ToolRecord`).

With no tools grant, or when no licence came back, the shell reads the packaged table
(`licences.yaml`) as before, records that read as a `retrieval` span, and says so in
`limitations`. Both paths are `retrieval` grounding, since an agent declares one mode.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from dd_agent_advisor_rights.interpret import key
from dd_sdk.agent import RunContext
from dd_sdk.contract.models import EvidenceItem, GroundingRef
from dd_sdk.evidence import DOCUMENT_CANONICALISATION, HASH_ALGORITHM, content_hash
from dd_sdk.tools import ToolGatewayError, ToolRecord, ToolUse
from dd_sdk.tracing import retrieval_span

SERVER = "spdx"
TOOL = "get_licence"
USES = (ToolUse(SERVER, (TOOL,)),)
TABLE_SOURCE = "advisor-rights:licences.yaml"
SPDX_URL = "https://spdx.org/licenses/{}.html"

PACKAGED = (
    "Its licences come from a short fixed list packaged with it, not from the SPDX licence list: "
    "it was granted no tool server for SPDX."
)
RETRIEVED = (
    "Its licences were retrieved from the SPDX licence list through the tool gateway, which names "
    "no licence text; the reuse each fits is the adviser's own judgement from its table."
)
FALLBACK = (
    "No licence could be retrieved from the SPDX licence list ({why}), so the licences come from "
    "a short fixed list packaged with the adviser."
)
LEFT_OUT = "{ids} could not be retrieved from the SPDX licence list ({why}), so not offered."


@dataclass(frozen=True)
class Licences:
    """The closed set and what it rests on. `table` is the table the interpreter and the rules
    work from; `cited` maps each licence's key to the record that grounds it, or is empty where
    one packaged table grounds them all (`shared`)."""

    table: Mapping[str, Any]
    limitation: str
    cited: Mapping[str, ToolRecord]
    shared: tuple[GroundingRef, EvidenceItem] | None = None
    left_out: str | None = None

    def limitations(self) -> list[str]:
        return [self.limitation, *([self.left_out] if self.left_out else [])]

    def cite(self, listed: Iterable[str]) -> tuple[list[GroundingRef], list[EvidenceItem]]:
        """The references and evidence for the licences listed, one record each."""
        if self.shared is not None:
            return [self.shared[0]], [self.shared[1]]
        records = [self.cited[k] for k in dict.fromkeys(key(i) for i in listed) if k in self.cited]
        records = records or list(self.cited.values())  # a succeeded payload must rest on one
        return [r.ref() for r in records], [r.evidence() for r in records]


def _packaged(
    table: Mapping[str, Any], ctx: RunContext, limitation: str, left: str | None = None
) -> Licences:
    """The packaged table, retrieved under one span so that what the payload cites was read."""
    document = {"licences": list(table["licences"])}
    digest = content_hash(document, DOCUMENT_CANONICALISATION)
    with retrieval_span(ctx.tracer, TABLE_SOURCE, digest):
        pass
    item = EvidenceItem(
        source_id=TABLE_SOURCE,
        retrieved_at=datetime.now(UTC),
        hash_algorithm=HASH_ALGORITHM,
        canonicalisation=DOCUMENT_CANONICALISATION,
        content_hash=digest,
        content=document,
    )
    ref = GroundingRef(source_id=TABLE_SOURCE, content_hash=digest)
    return Licences(table, limitation, {}, (ref, item), left)


def _fetch(ctx: RunContext, spdx_id: str) -> tuple[ToolRecord | None, str]:
    """The record the gateway returned for one licence, or why there is none."""
    assert ctx.tools is not None
    try:
        outcome = ctx.tools.call(SERVER, TOOL, {"id": spdx_id})
    except ToolGatewayError as error:
        return None, f"the gateway refused the call: {error}"
    if outcome.is_error or not outcome.records:
        return None, "the server returned no record"
    return outcome.records[0], ""


def retrieve(table: Mapping[str, Any], mandated: str | None, ctx: RunContext) -> Licences:
    """The licences to work from: the table's rows the gateway returned, and a mandated licence
    the table lacks if it did too. With no grant, or none returned, the packaged table."""
    if ctx.tools is None:
        return _packaged(table, ctx, PACKAGED)
    rows: list[dict[str, Any]] = list(table["licences"])
    outside = (mandated or "").strip()
    if outside and key(outside) not in {key(r["spdx_id"]) for r in rows}:
        url = SPDX_URL.format(outside)
        rows.append({"spdx_id": outside, "name": outside, "url": url, "fits": [], "note": None})
    kept: list[dict[str, Any]] = []
    cited: dict[str, ToolRecord] = {}
    missing: dict[str, str] = {}
    for row in rows:
        record, why = _fetch(ctx, row["spdx_id"])
        if record is None:
            missing[row["spdx_id"]] = why
            continue
        cited[key(row["spdx_id"])] = record
        name = record.content.get("name")
        kept.append({**row, "name": name if isinstance(name, str) and name else row["name"]})
    why = "; ".join(sorted(set(missing.values())))
    if not kept:
        return _packaged(table, ctx, FALLBACK.format(why=why))
    left = LEFT_OUT.format(ids=", ".join(missing), why=why) if missing else None
    return Licences({**table, "licences": kept}, RETRIEVED, cited, None, left)
