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

import base64
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal

from dd_harness.projects import APPROVED, PROPOSED
from dd_harness.provenance import AGENT_BASE
from dd_harness.storage import ProjectStorage, RunStorage
from dd_sdk.contract.models import now

# Where a model is named, beside the agents (TODO(#3): the w3id namespace is not yet registered).
MODEL_BASE = "https://w3id.org/data-director/models/"

type Origin = Literal["model", "model_revised", "template", "template_revised", "person"]

# The IPTC Digital Source Type vocabulary, as schema.org's `digitalSourceType` takes it.
IPTC = "http://cv.iptc.org/newscodes/digitalsourcetype/"
DIGITAL_SOURCE_TYPE: dict[Origin, str | None] = {
    "model": IPTC + "trainedAlgorithmicMedia",
    "model_revised": IPTC + "compositeWithTrainedAlgorithmicMedia",
    "template": IPTC + "algorithmicMedia",
    "template_revised": IPTC + "algorithmicMedia",
    "person": None,
}
# How a statement names a document kind (dd_sdk DocumentKind).
KIND_NAMES = {
    "metadata_record": "Metadata record",
    "readme": "README",
    "data_dictionary": "Data dictionary",
    "dmp": "Data management plan",
}
CONTEXT = {
    "prov": "http://www.w3.org/ns/prov#",
    "schema": "http://schema.org/",
    "dd": "https://w3id.org/data-director/",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}


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
    # Each version from the first draft to the approved one, oldest first (for the graph).
    chain: tuple[dict[str, Any], ...] = field(repr=False)

    @property
    def name(self) -> str:
        kind = KIND_NAMES.get(self.document_kind, self.document_kind.replace("_", " "))
        return f"{kind}: {self.document_title}" if self.document_title else kind


@dataclass(frozen=True)
class Disclosure:
    project_id: str
    made_at: datetime
    documents: tuple[DocumentDisclosure, ...]
    # Documents with a version still awaiting a decision and none approved.
    pending: int

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
        """A PROV-O account of each approved version, in JSON-LD with an inline context."""
        graph: dict[str, dict[str, Any]] = {}

        def put(node: dict[str, Any]) -> None:
            graph.setdefault(node["@id"], {}).update(node)

        for d in self.documents:
            for link in d.chain:
                _version_nodes(put, d, link)
        return {"@context": CONTEXT, "@graph": list(graph.values())}


def disclose(projects: ProjectStorage, runs: RunStorage, project_id: str) -> Disclosure:
    """The disclosure of a project's approved documents. Raises `UnknownProjectError` for an
    unknown project."""
    found: list[DocumentDisclosure] = []
    pending = 0
    for document in projects.documents(project_id):
        versions = document["versions"]
        approved = [v for v in versions if v["state"] == APPROVED]
        if not approved:
            pending += any(v["state"] == PROPOSED for v in versions)
            continue
        found.append(_disclose(runs, document, approved[-1]))
    return Disclosure(project_id, now(), tuple(found), pending)


def _disclose(
    runs: RunStorage, document: dict[str, Any], version: dict[str, Any]
) -> DocumentDisclosure:
    chain = version_chain(document, version)
    drafted = next((v for v in reversed(chain) if v.get("drafted_by")), None)
    draft = _draft(runs, drafted["drafted_by"]) if drafted else None
    after = chain[chain.index(drafted) + 1 :] if drafted else chain
    edited_by = tuple(v["added_by"]["name"] for v in after if not v.get("drafted_by"))
    origin: Origin
    if draft is None:
        origin = "person"
    elif draft.derivation == "model":
        origin = "model_revised" if edited_by else "model"
    else:
        origin = "template_revised" if edited_by else "template"
    decision = version["decision"]
    return DocumentDisclosure(
        document_id=document["document_id"],
        document_kind=document["document_kind"],
        document_title=version.get("document_title"),
        version=version["version"],
        digest=version["digest"],
        origin=origin,
        draft=draft,
        edited_by=edited_by,
        approved_by=decision["decided_by"]["name"],
        approved_at=decision["decided_at"],
        reason=decision.get("reason"),
        chain=tuple(
            {**v, "document_id": document["document_id"], "draft": _draft_of(runs, v)}
            for v in chain
        ),
    )


def version_chain(document: dict[str, Any], version: dict[str, Any]) -> list[dict[str, Any]]:
    """The versions from the first a version revises back to, to the version, oldest first."""
    by_number = {v["version"]: v for v in document["versions"]}
    chain = [version]
    while (revises := chain[0].get("revises")) and revises["version"] in by_number:
        if revises["document_id"] != document["document_id"]:
            break
        chain.insert(0, by_number[revises["version"]])
    return chain


def _draft_of(runs: RunStorage, version: dict[str, Any]) -> Draft | None:
    drafted_by = version.get("drafted_by")
    return _draft(runs, drafted_by) if drafted_by else None


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


def _version_nodes(put: Any, d: DocumentDisclosure, link: dict[str, Any]) -> None:
    """The PROV nodes for one version of the chain: the version, what generated it, and, for the
    approved version, its approval."""
    vid = version_id(link["document_id"], link["version"])
    node: dict[str, Any] = {
        "@id": vid,
        "@type": ["prov:Entity", "schema:CreativeWork"],
        "schema:name": d.name,
        "schema:additionalType": d.document_kind,
        "schema:sha256": link["digest"],
        "schema:version": link["version"],
    }
    if revises := link.get("revises"):
        node["prov:wasRevisionOf"] = {"@id": version_id(link["document_id"], revises["version"])}
    draft: Draft | None = link["draft"]
    if draft is not None:
        agent = AGENT_BASE + draft.agent_id
        run = f"urn:uuid:{draft.invocation_id}"
        put(
            {
                "@id": agent,
                "@type": ["prov:SoftwareAgent", "schema:SoftwareApplication"],
                "schema:name": draft.agent_id,
            }
        )
        activity: dict[str, Any] = {
            "@id": run,
            "@type": "prov:Activity",
            "prov:wasAssociatedWith": {"@id": agent},
            "schema:softwareVersion": draft.agent_version,
            "dd:derivation": draft.derivation,
        }
        if draft.completed_at:
            activity["prov:endedAtTime"] = _datetime(draft.completed_at)
        calls = []
        for n, m in enumerate(draft.models, start=1):
            model = f"{MODEL_BASE}{m.provider or 'unknown'}/{m.model_id}"
            put(
                {
                    "@id": model,
                    "@type": ["prov:SoftwareAgent", "schema:SoftwareApplication"],
                    "schema:name": m.model_id,
                    **({"schema:provider": m.provider} if m.provider else {}),
                }
            )
            call: dict[str, Any] = {
                "@id": f"{run}#model-call-{n}",
                "@type": "prov:Activity",
                "prov:wasAssociatedWith": {"@id": model},
            }
            if m.called_at:
                call["prov:startedAtTime"] = _datetime(m.called_at)
            if m.prompt_digest:
                prompt = ni(m.prompt_digest)
                put(
                    {
                        "@id": prompt,
                        "@type": ["prov:Entity", "prov:Plan"],
                        "schema:name": "Prompt sent to the model",
                        "schema:sha256": m.prompt_digest,
                    }
                )
                call["prov:used"] = {"@id": prompt}
                call["prov:qualifiedAssociation"] = {
                    "@type": "prov:Association",
                    "prov:agent": {"@id": model},
                    "prov:hadPlan": {"@id": prompt},
                }
            put(call)
            calls.append({"@id": call["@id"]})
        if calls:
            activity["prov:wasInformedBy"] = calls
        put(activity)
        node["prov:wasGeneratedBy"] = {"@id": run}
        node["prov:wasAttributedTo"] = {"@id": agent}
    else:
        person = _person(put, link["added_by"])
        edit = f"{vid}-edit"
        put(
            {
                "@id": edit,
                "@type": "prov:Activity",
                "prov:wasAssociatedWith": {"@id": person},
                "prov:endedAtTime": _datetime(link["added_at"]),
            }
        )
        node["prov:wasGeneratedBy"] = {"@id": edit}
        node["prov:wasAttributedTo"] = {"@id": person}
    if link["version"] == d.version:
        source_type = DIGITAL_SOURCE_TYPE[d.origin]
        if source_type:
            node["schema:digitalSourceType"] = {"@id": source_type}
        decision = link["decision"]
        person = _person(put, decision["decided_by"])
        approval: dict[str, Any] = {
            "@id": f"{vid}-approval",
            "@type": "prov:Activity",
            "schema:name": "approval",
            "prov:used": {"@id": vid},
            "prov:wasAssociatedWith": {"@id": person},
            "prov:endedAtTime": _datetime(decision["decided_at"]),
        }
        if decision.get("reason"):
            approval["schema:description"] = decision["reason"]
        put(approval)
    put(node)


def _person(put: Any, principal: dict[str, Any]) -> str:
    put(
        {
            "@id": principal["principal_id"],
            "@type": ["prov:Person", "schema:Person"],
            "schema:name": principal["name"],
        }
    )
    return str(principal["principal_id"])


def version_id(document_id: str, version: int) -> str:
    return f"urn:uuid:{document_id}#v{version}"


def ni(digest: str) -> str:
    """The RFC 6920 `ni` URI of a SHA-256 hex digest."""
    raw = bytes.fromhex(digest)
    return "ni:///sha-256;" + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _datetime(value: str) -> dict[str, str]:
    return {"@value": value, "@type": "xsd:dateTime"}


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
