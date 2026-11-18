"""Shapes the core contract defines (`dd_sdk.contract`), as a response model names them (#1130).

A response model does not mirror a contract class: it holds the document as the JSON object the
harness stored or made, and its JSON Schema names the contract's own TypeScript type (`tsType`),
so the generated interfaces refer to that type rather than to a copy that could drift from it.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import WithJsonSchema


def _named(contract_class: str) -> WithJsonSchema:
    return WithJsonSchema({"type": "object", "tsType": contract_class})


Principal = Annotated[dict[str, Any], _named("Principal")]
"""Whom a change acted for, as the project log records it."""
DocumentVersionRef = Annotated[dict[str, Any], _named("DocumentVersionRef")]
DocumentQuestion = Annotated[dict[str, Any], _named("DocumentQuestion")]
DocumentationSummary = Annotated[dict[str, Any], _named("DocumentationSummary")]
FileInventory = Annotated[dict[str, Any], _named("FileInventory")]
ProjectFact = Annotated[dict[str, Any], _named("ProjectFact")]
RepositoryRequirements = Annotated[dict[str, Any], _named("RepositoryRequirements")]
ResearcherRecord = Annotated[dict[str, Any], _named("ResearcherRecord")]
