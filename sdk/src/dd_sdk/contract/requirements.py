"""Pydantic mirrors of the requirement sets (schema/data_director.yaml, docs/specs/deposit.md):
what a deposit must or should have, as the deployment's configuration says it, which the harness
loads and merges for the repository a researcher chose. Not an input or a payload of any agent.
`dd_sdk.contract.models` re-exports every class."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from dd_sdk.contract.base import (
    RE3DATA_ID_PATTERN,
    REPOSITORY_ID_PATTERN,
    SHA256_PATTERN,
    Frozen,
    backfill_repository_id,
)
from dd_sdk.contract.deposit import DepositConnector, Obligation
from dd_sdk.contract.facts import DocumentKind


class RequirementField(Frozen):
    property: str
    qualifier: dict[str, Any] | None = None
    schema_org: str
    obligation: Obligation
    form_label: str | None = None


class _Requirements(Frozen):
    """What a requirement set and a merged choice of repository both state."""

    conforms_to: str
    fields: list[RequirementField] = Field(default_factory=list)
    required_documents: list[DocumentKind] = Field(default_factory=list)
    recommended_documents: list[DocumentKind] = Field(default_factory=list)
    media_types: list[str] = Field(default_factory=list)
    max_file_size: int | None = None
    max_item_size: int | None = None
    licences: list[str] | None = None
    guidance: list[str] = Field(default_factory=list)
    unconfirmed: list[str] = Field(default_factory=list)
    deposit: DepositConnector | None = None


class RequirementSet(_Requirements):
    """A metadata standard's requirements, or one repository's override of them
    (docs/specs/deposit.md)."""

    schema_class: Literal["RequirementSet"] = "RequirementSet"
    requirement_set_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: int
    title: str
    url: str | None = None
    re3data_names: list[str] = Field(default_factory=list)
    re3data_id: str | None = Field(default=None, pattern=RE3DATA_ID_PATTERN)
    # An override for a repository re3data does not list names its DataCite identifier instead.
    repository_id: str | None = Field(default=None, pattern=REPOSITORY_ID_PATTERN)


class RequirementSetUse(Frozen):
    ref: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*@v[0-9]+$")
    sha256: str = Field(pattern=SHA256_PATTERN)


class RepositoryRequirements(_Requirements):
    """The merged requirements of the repository a researcher chose (docs/specs/deposit.md).
    `repository_id` is its re3data identifier where re3data lists it, else its DataCite one; a
    set kept before there was one names only `re3data_id`, which then gives it."""

    repository_id: str = Field(pattern=REPOSITORY_ID_PATTERN)
    re3data_id: str | None = Field(default=None, pattern=RE3DATA_ID_PATTERN)
    repository_name: str
    requirement_sets: list[RequirementSetUse]
    warnings: list[str] = Field(default_factory=list)
    repository_url: str | None = None

    _backfill = model_validator(mode="before")(
        backfill_repository_id("repository_id", "re3data_id")
    )
