"""Doubles for this agent's tests: a model's reply in the shape its schema asks for, and a
README request as a project's second run makes it."""

from __future__ import annotations

import json
from collections.abc import Mapping

from dd_agent_advisor_documentation.prose import OVERVIEW
from dd_sdk.contract.models import (
    CurrentVersion,
    DocumentKind,
    DocumentVersionRef,
    DraftRequest,
    VersionState,
    new_invocation_id,
)


def prose_reply(paragraphs: Mapping[str, str | None]) -> str:
    """A `ProseReply` as a model sends it: the overview under `overview`, the rest by heading."""
    return json.dumps(
        {
            "overview": paragraphs.get(OVERVIEW),
            "sections": [
                {"section": heading, "paragraph": paragraph}
                for heading, paragraph in paragraphs.items()
                if heading != OVERVIEW
            ],
        }
    )


def suggestion_reply(answers: Mapping[str, str | None]) -> str:
    """A `SuggestionReply` as a model sends it: a suggestion by question identifier."""
    return json.dumps(
        {"suggestions": [{"question_id": q, "answer": a} for q, a in answers.items()]}
    )


def redraft(asked: DraftRequest) -> DraftRequest:
    """`asked` as the README's second run in a project, after the `questions` version the first
    run made: the editor then writes the README itself, from whatever answers it has
    (docs/specs/drafting.md). A request that already names a current version is left as it is."""
    if asked.document_kind != DocumentKind.README or asked.current_version is not None:
        return asked
    note = CurrentVersion(
        version_ref=DocumentVersionRef(document_id=new_invocation_id(), version=1),
        document_title="README",
        media_type="text/markdown",
        document_text="# README\n\n_This is not the README yet._\n",
        version_state=VersionState.PROPOSED,
    )
    return asked.model_copy(update={"current_version": note})
