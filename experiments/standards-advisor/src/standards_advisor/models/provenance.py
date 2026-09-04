"""§6.3 — a PROV-O graph per run (C12).

C12 is one of the two controls §3 marks as impossible to add later: by the time you go looking,
the evidence is gone. So this is written from the first commit even though the pipeline it
describes is mostly stubs.

JSON-LD keys are supplied as field aliases and emitted with `by_alias=True`. The generated JSON
Schema for this document describes its *shape* only — JSON Schema cannot express PROV-O
conformance, and `schemas/README.md` says so.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field

PROV_CONTEXT: dict[str, str] = {
    "prov": "http://www.w3.org/ns/prov#",
    "dd": "urn:dd:r3:",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


class ProvNode(BaseModel):
    """Base for a node in the graph. Aliased fields, populated by field name in code."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    id: str = Field(alias="@id")
    type: str | list[str] = Field(alias="@type")


class ProvEntity(ProvNode):
    label: str | None = Field(default=None, alias="prov:label")
    generated_by: str | None = Field(default=None, alias="prov:wasGeneratedBy")
    derived_from: list[str] | None = Field(default=None, alias="prov:wasDerivedFrom")
    value: str | None = Field(default=None, alias="prov:value")
    dd_sha256: str | None = Field(default=None, alias="dd:sha256")
    dd_version: str | None = Field(default=None, alias="dd:version")
    dd_path: str | None = Field(default=None, alias="dd:path")


class EnergyEstimate(BaseModel):
    """An optional extra, per §6.3 — "cheap now, awkward later".

    Token counts only. Converting tokens to energy needs a factor that is a research question,
    not a constant to invent here, so the field records the inputs and stops.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    model_calls: int = 0


class ProvActivity(ProvNode):
    label: str | None = Field(default=None, alias="prov:label")
    started_at: str | None = Field(default=None, alias="prov:startedAtTime")
    ended_at: str | None = Field(default=None, alias="prov:endedAtTime")
    used: list[str] = Field(default_factory=list, alias="prov:used")
    associated_with: list[str] = Field(default_factory=list, alias="prov:wasAssociatedWith")
    informed_by: str | None = Field(default=None, alias="prov:wasInformedBy")
    dd_status: str | None = Field(default=None, alias="dd:status")
    dd_counts: dict[str, int] | None = Field(default=None, alias="dd:counts")
    dd_energy: EnergyEstimate | None = Field(default=None, alias="dd:energyEstimate")


class ProvAgent(ProvNode):
    label: str | None = Field(default=None, alias="prov:label")
    dd_version: str | None = Field(default=None, alias="dd:version")
    dd_model_params: dict[str, str] | None = Field(default=None, alias="dd:modelParameters")


class ProvDocument(BaseModel):
    """The whole graph for one run."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    CONTEXT: ClassVar[dict[str, str]] = PROV_CONTEXT

    context: dict[str, str] = Field(default_factory=lambda: dict(PROV_CONTEXT), alias="@context")
    graph: list[ProvEntity | ProvActivity | ProvAgent] = Field(default_factory=list, alias="@graph")

    def to_jsonld(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, exclude_none=True)
