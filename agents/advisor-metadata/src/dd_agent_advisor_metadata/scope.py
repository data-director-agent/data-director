"""What the librarian drafts, and the stop for a request it does not: a document other than a
metadata record (`outside_agent_scope`), no repository chosen (`insufficient_input`), or
requirements in a standard other than DataCite (`capability_not_implemented`, R6; conversion
between standards is TODO(#1363))."""

from __future__ import annotations

from dd_sdk.agent import AgentResult, abstain
from dd_sdk.contract.models import DocumentKind, DraftRequest, ReasonCode, RepositoryRequirements

# The schema every record follows in the MVP (docs/specs/deposit.md).
DATACITE = "http://datacite.org/schema/kernel-4"


def drafted(asked: DraftRequest) -> RepositoryRequirements | AgentResult:
    """The requirements the record is drafted to, or the stop for a request the librarian does
    not draft."""
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
    if requirements.conforms_to != DATACITE:
        return abstain(
            ReasonCode.CAPABILITY_NOT_IMPLEMENTED,
            f"The librarian drafts DataCite records only, not {requirements.conforms_to}, "
            "and does not convert a record to another standard.",
        )
    return requirements
