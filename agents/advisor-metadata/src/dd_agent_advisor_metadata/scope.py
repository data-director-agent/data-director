"""What the librarian drafts, and the stop for a request it does not: a document other than a
metadata record (`outside_agent_scope`), no repository chosen (`insufficient_input`), or
requirements in a standard no registered definition covers (`capability_not_implemented`, R6;
conversion between standards is TODO(#1363)).

A standard is drafted in from its registered definition (docs/specs/metadata-standards.md), so a
standard is available to the librarian by being installed.
"""

from __future__ import annotations

from functools import cache

from dd_metadata_records import Standard, Standards, discover
from dd_sdk.agent import AgentResult, abstain
from dd_sdk.contract.models import DocumentKind, DraftRequest, ReasonCode, RepositoryRequirements

# The standard most repositories' requirements follow, by its `conforms_to` URI
# (docs/specs/deposit.md).
DATACITE = "http://datacite.org/schema/kernel-4"


@cache
def standards() -> Standards:
    """The registered standards, found once per process."""
    return discover()


def drafted(
    asked: DraftRequest, registered: Standards | None = None
) -> tuple[RepositoryRequirements, Standard] | AgentResult:
    """The requirements the record is drafted to and the standard it is drafted in, or the stop
    for a request the librarian does not draft."""
    if asked.document_kind != DocumentKind.METADATA_RECORD:
        return abstain(
            ReasonCode.OUTSIDE_AGENT_SCOPE,
            f"The Metadata Librarian drafts a metadata record, not a {asked.document_kind.value}.",
        )
    requirements = asked.requirements
    if requirements is None:
        return abstain(
            ReasonCode.INSUFFICIENT_INPUT,
            "Choose a repository first: the record has the properties it asks for.",
        )
    standard = (registered or standards()).by_uri(requirements.conforms_to)
    if standard is None:
        return abstain(
            ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
            "The librarian drafts only in a standard a registered definition covers, not "
            f"{requirements.conforms_to}, and does not convert a record to another standard.",
        )
    return requirements, standard


def unwritable(name: str, requirements: RepositoryRequirements, why: Exception) -> AgentResult:
    """The stop for requirements that name a property the standard's serialisation has no place
    for, such as a DataCite property in a set that says it follows Dublin Core."""
    return abstain(
        ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
        f"The record cannot be written in {name}: {why}. The requirements of "
        f"{requirements.repository_name} name a property the standard has no place for.",
    )
