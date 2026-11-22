"""What a project's documents owe to generative AI, read from the record (docs/specs/disclosure.md).

`disclose` reads the project log and the run store and never writes either. For each document
with an approved version, it takes the latest approved version and follows its `revises` chain
back to the run that drafted it, if any. The version is then one of:

- `model`: drafted by an agent with a language model, and approved as drafted;
- `model_revised`: drafted with a language model, then edited and approved by a person;
- `template`: drafted by an agent by rule, with no generative model, and approved as drafted;
- `template_revised`: drafted by rule, then edited and approved by a person;
- `person`: written by a person.

The models are those the drafting run's envelope records (`telemetry.model_calls`), with the
date of each call and the digest of each prompt. A version that is not approved is not disclosed:
it is not part of what a researcher would publish. The disclosure is rendered as a statement a
person reads and as a PROV-O graph in JSON-LD.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from dd_harness.document_origin import DIGITAL_SOURCE_TYPE as DIGITAL_SOURCE_TYPE
from dd_harness.document_origin import IPTC as IPTC
from dd_harness.document_origin import KIND_NAMES as KIND_NAMES
from dd_harness.document_origin import Origin, document_name, drafted_in, edited_after_draft
from dd_harness.document_origin import origin as origin_of
from dd_harness.document_origin import version_chain as chain_of
from dd_harness.projects import APPROVED, PROPOSED
from dd_harness.provenance_graph import CONTEXT as CONTEXT
from dd_harness.provenance_graph import project_graph
from dd_harness.provenance_graph.nodes import MODEL_BASE as MODEL_BASE
from dd_harness.provenance_graph.nodes import ni as ni
from dd_harness.provenance_graph.nodes import version_id as version_id
from dd_harness.storage import ProjectDocuments, RunStorage
from dd_sdk.contract.models import now


@dataclass(frozen=True)
class ModelUsed:
    """One call to a language model, as the drafting run recorded it."""

    provider: str
    model_id: str
    called_at: str
    prompt_digest: str | None


@dataclass(frozen=True)
class Draft:
    """The run that drafted the text a version starts from."""

    agent_id: str
    agent_version: str
    invocation_id: str
    derivation: str
    completed_at: str | None
    models: tuple[ModelUsed, ...]


@dataclass(frozen=True)
class DocumentDisclosure:
    document_id: str
    document_kind: str
    document_title: str | None
    version: int
    digest: str
    origin: Origin
    draft: Draft | None
    # People who edited the text after the draft, oldest first, by name.
    edited_by: tuple[str, ...]
    approved_by: str
    approved_at: str
    reason: str | None

    @property
    def name(self) -> str:
        return document_name(self.document_kind, self.document_title)


@dataclass(frozen=True)
class Disclosure:
    project_id: str
    made_at: datetime
    documents: tuple[DocumentDisclosure, ...]
    # Documents with a version still awaiting a decision and none approved.
    pending: int
    # The part of the project's provenance graph reachable from each approved version.
    graph: dict[str, Any] = field(repr=False, default_factory=dict)

    def to_document(self) -> dict[str, Any]:
        """The disclosure as JSON, for the app."""
        return {
            "project_id": self.project_id,
            "made_at": self.made_at.isoformat(),
            "pending": self.pending,
            "statement": self.statement(),
            "documents": [
                {
                    "document_id": d.document_id,
                    "document_kind": d.document_kind,
                    "document_title": d.document_title,
                    "version": d.version,
                    "digest": d.digest,
                    "origin": d.origin,
                    "draft": None
                    if d.draft is None
                    else {
                        "agent_id": d.draft.agent_id,
                        "agent_version": d.draft.agent_version,
                        "invocation_id": d.draft.invocation_id,
                        "derivation": d.draft.derivation,
                        "completed_at": d.draft.completed_at,
                        "models": [
                            {
                                "provider": m.provider,
                                "model_id": m.model_id,
                                "called_at": m.called_at,
                                "prompt_digest": m.prompt_digest,
                            }
                            for m in d.draft.models
                        ],
                    },
                    "edited_by": list(d.edited_by),
                    "approved_by": d.approved_by,
                    "approved_at": d.approved_at,
                    "reason": d.reason,
                }
                for d in self.documents
            ],
        }

    def statement(self) -> str:
        """A statement of the use of generative AI a person can read and cite, in Markdown."""
        lines = ["# Use of generative AI", ""]
        generated = [d for d in self.documents if d.origin in ("model", "model_revised")]
        if not self.documents:
            lines.append("No document of this project has been approved yet.")
        elif not generated:
            lines.append(
                "No generative AI model was used to produce the approved documents of this project."
            )
        else:
            models = sorted(
                {_model_name(m) for d in generated if d.draft for m in d.draft.models}
            ) or ["a generative AI model whose name was not recorded"]
            lines.append(
                f"Of the {_count(len(self.documents), 'approved document')} of this project, "
                f"{len(generated)} {'was' if len(generated) == 1 else 'were'} drafted with "
                f"generative AI through the Data Director, using {_join(models)}. A person "
                "validated each document before approving it, as recorded below."
            )
        for d in self.documents:
            lines += ["", f"## {d.name}", "", _sentence(d)]
            if d.draft and d.draft.models:
                digests = sorted({m.prompt_digest for m in d.draft.models if m.prompt_digest})
                if digests:
                    lines.append("")
                    lines.append(
                        f"{_count(len(digests), 'prompt')} sent to the model "
                        f"{'is' if len(digests) == 1 else 'are'} kept with the project's record, "
                        f"by SHA-256: {', '.join(digests)}."
                    )
        if self.pending:
            lines += [
                "",
                f"{_count(self.pending, 'other document')} "
                f"{'awaits' if self.pending == 1 else 'await'} a decision and "
                f"{'is' if self.pending == 1 else 'are'} not covered by this statement.",
            ]
        lines += [
            "",
            f"Statement made by the Data Director on {_date(self.made_at.isoformat())} from the "
            f"project's record ({self.project_id}).",
        ]
        return "\n".join(lines) + "\n"

    def prov_jsonld(self) -> dict[str, Any]:
        """A PROV-O account of each approved version, in JSON-LD with an inline context: the
        part of the project's provenance graph reachable from each approved version and its
        approval (docs/specs/provenance.md, invariant 10)."""
        return self.graph


def disclose(projects: ProjectDocuments, runs: RunStorage, project_id: str) -> Disclosure:
    """The disclosure of a project's approved documents. Raises `UnknownProjectError` for an
    unknown project."""
    found: list[DocumentDisclosure] = []
    pending = 0
    seeds: list[str] = []
    for document in projects.documents(project_id):
        versions = document["versions"]
        approved = [v for v in versions if v["state"] == APPROVED]
        if not approved:
            pending += any(v["state"] == PROPOSED for v in versions)
            continue
        found.append(_disclose(runs, document, approved[-1]))
        seeds.append(version_id(document["document_id"], approved[-1]["version"]))
    graph = project_graph(projects, runs, project_id)
    seeds += [graph.approvals[(d.document_id, d.version)] for d in found]
    return Disclosure(project_id, now(), tuple(found), pending, graph.subgraph(seeds))


def _disclose(
    runs: RunStorage, document: dict[str, Any], version: dict[str, Any]
) -> DocumentDisclosure:
    chain = version_chain(document, version)
    drafted = drafted_in(chain)
    draft = _draft(runs, drafted["drafted_by"]) if drafted else None
    decision = version["decision"]
    return DocumentDisclosure(
        document_id=document["document_id"],
        document_kind=document["document_kind"],
        document_title=version.get("document_title"),
        version=version["version"],
        digest=version["digest"],
        origin=origin_of(chain),
        draft=draft,
        edited_by=tuple(v["added_by"]["name"] for v in edited_after_draft(chain)),
        approved_by=decision["decided_by"]["name"],
        approved_at=decision["decided_at"],
        reason=decision.get("reason"),
    )


def version_chain(document: dict[str, Any], version: dict[str, Any]) -> list[dict[str, Any]]:
    """The versions from the first a version revises back to, to the version, oldest first."""
    return chain_of(document["document_id"], document["versions"], version)


def _draft(runs: RunStorage, drafted_by: dict[str, Any]) -> Draft:
    envelope = runs.get(drafted_by["invocation_id"]) or {}
    telemetry = envelope.get("telemetry", {})
    models = tuple(
        ModelUsed(c["model_provider"], c["model_id"], c["called_at"], c["prompt_digest"])
        for c in telemetry.get("model_calls", [])
    )
    if not models and telemetry.get("model_id"):
        # A run stored before calls were recorded names its model only.
        models = (ModelUsed("", telemetry["model_id"], envelope.get("completed_at", ""), None),)
    return Draft(
        agent_id=drafted_by["agent_id"],
        agent_version=drafted_by["agent_version"],
        invocation_id=drafted_by["invocation_id"],
        derivation=drafted_by["document_derivation"],
        completed_at=envelope.get("completed_at"),
        models=models,
    )


def _sentence(d: DocumentDisclosure) -> str:
    """How one approved version came about, in a sentence or three."""
    edited = _join(sorted(set(d.edited_by)))
    on = _date(d.approved_at)
    if d.edited_by and set(d.edited_by) == {d.approved_by}:
        after = f"{d.approved_by} revised the text and approved it on {on}."
    elif d.edited_by:
        after = f"{edited} revised the text, and {d.approved_by} approved it on {on}."
    else:
        after = f"{d.approved_by} approved it without change on {on}."
    reason = f" Reason given: {_sentence_end(d.reason)}" if d.reason else ""
    if d.draft is None:
        return f"Written by {edited or 'a person'}, with no generative AI. {after}{reason}"
    agent = f"{d.draft.agent_id} {d.draft.agent_version}"
    when = _date(d.draft.completed_at or "")
    if d.origin in ("model", "model_revised"):
        used = _join(sorted({_model_name(m) for m in d.draft.models})) or (
            "a generative AI model whose name was not recorded"
        )
        drafted = f"Drafted on {when} by the Data Director agent {agent}, using {used}."
        if d.origin == "model":
            drafted += " The approved text is that model output, reproduced verbatim."
    else:
        drafted = (
            f"Drafted on {when} by the Data Director agent {agent}, by rule from the project's "
            "record, with no generative AI."
        )
    return f"{drafted} {after}{reason}"


def _sentence_end(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else text + "."


def _model_name(m: ModelUsed) -> str:
    return f"{m.model_id} ({m.provider})" if m.provider else m.model_id


def _date(value: str) -> str:
    return value[:10] if value else "an unrecorded date"


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}{'' if n == 1 else 's'}"


def _join(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]
