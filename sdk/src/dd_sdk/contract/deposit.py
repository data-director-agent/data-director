"""Pydantic mirrors of what a requirement set says of a deposit beyond its fields
(schema/data_director.yaml, docs/specs/deposit.md): how much a field or document is needed
(`Obligation`), where a researcher supplies a value (`SuppliedOn`), and the API an override says
a draft is deposited through (`DepositConnector`). `dd_sdk.contract.models` re-exports the first
and the last."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from dd_sdk.contract.base import Frozen


class Obligation(StrEnum):
    REQUIRED = "required"
    RECOMMENDED = "recommended"


class SuppliedOn(StrEnum):
    """The page of a project where a researcher supplies a value a deposit needs."""

    DOCUMENTS = "documents"
    RESEARCHERS = "researchers"
    FACTS = "facts"
    REPOSITORY = "repository"


class DepositConnector(Frozen):
    """How the harness deposits a draft to one repository through its API: an override's
    `deposit` block (docs/specs/deposit.md). It holds no credential."""

    transport: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    format: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    base_url: str = Field(pattern=r"^https://")
    target: str | None = None
    sandbox: bool | None = None
