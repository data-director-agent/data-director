"""The input and payload classes of advisor.rights, as Pydantic models (docs/specs/contract.md).

`schema/rights.yaml` is the source; `ClassSchema.of` compares each model with the schema generated
from it.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from dd_sdk.contract.models import Derivation, Frozen, Grounded, ProjectFact


class RightsContext(Frozen):
    schema_class: Literal["RightsContext"] = "RightsContext"
    reuse_wanted: str | None = None
    sensitive: bool | None = None
    mandated_licence: str | None = None
    third_party_content: bool | None = None
    # Filled by the conductor in a project (`GivenProjectDecisions`).
    project_decisions: list[ProjectFact] = Field(default_factory=list)


class LicenceOption(Frozen):
    spdx_id: str
    name: str
    url: str
    note: str | None = None
    derivation: Derivation


class RightsQuestion(Frozen):
    text: str
    derivation: Derivation


class AccessOption(Frozen):
    level: str
    when: str


class RightsOptions(Grounded):
    schema_class: Literal["RightsOptions"] = "RightsOptions"
    licences: list[LicenceOption] = Field(default_factory=list)
    access_levels: list[AccessOption] = Field(default_factory=list)
    questions: list[RightsQuestion] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    dropped: list[str] = Field(default_factory=list)
