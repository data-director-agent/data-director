"""Process Run Crate for one invocation (R10), written with ro-crate-py.

The invocation is one `CreateAction`: the agent is the instrument, the human it acted for the agent
(Blueprint §5.4, docs/specs/policy-and-identity.md), the request the object, the envelope and the
span file the results. Each model call the agent made is a `CreateAction` of its own, with the
model as instrument and the prompt as object (docs/specs/disclosure.md). The prompt is named by its
`dd-prompt-json-v1` digest and is not in the crate: the run store keeps it.

The crate is built in a temporary directory and returned as its files, which the conductor keeps
as the run's `crate/...` artifacts (docs/specs/storage.md), so it does not depend on how the run
store keeps them.

Profile: https://w3id.org/ro/wfrun/process/0.5. This module is the only importer of `rocrate`
(docs/specs/dependencies.md).
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from rocrate.model import ContextEntity, Person, SoftwareApplication
from rocrate.rocrate import ROCrate

PROCESS_RUN_CRATE = "https://w3id.org/ro/wfrun/process/0.5"
AGENT_BASE = "https://w3id.org/data-director/agents/"
# The contract's `vouched_by` slot (dd:vouched_by), a term of the crate's context
# (docs/specs/policy-and-identity.md).
VOUCHED_BY = "vouchedBy"
VOUCHED_BY_IRI = "https://w3id.org/data-director/vouched_by"


def process_run_crate(
    envelope: dict[str, Any],
    request: dict[str, Any],
    spans: bytes | None,
    started_at: datetime,
) -> dict[str, bytes]:
    """The Process Run Crate of one invocation, as its files: each path relative to the crate's
    root, with its bytes. The envelope and request are written as the run store writes them."""
    with tempfile.TemporaryDirectory(prefix="dd-crate-") as tmp:
        work = Path(tmp)
        request_path = work / "request.json"
        request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
        envelope_path = work / "envelope.json"
        envelope_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        spans_path = None
        if spans is not None:
            spans_path = work / "spans.jsonl"
            spans_path.write_bytes(spans)
        out = work / "crate"
        _write_crate(out, envelope, request_path, envelope_path, spans_path, started_at)
        return {
            path.relative_to(out).as_posix(): path.read_bytes()
            for path in sorted(out.rglob("*"))
            if path.is_file()
        }


def _write_crate(
    out: Path,
    envelope: dict[str, Any],
    request_path: Path,
    envelope_path: Path,
    spans_path: Path | None,
    started_at: datetime,
) -> None:
    crate = ROCrate()
    crate.root_dataset["conformsTo"] = {"@id": PROCESS_RUN_CRATE}
    crate.root_dataset["name"] = f"Data Director invocation {envelope['invocation_id']}"
    crate.root_dataset["description"] = (
        "Process Run Crate for one Data Director agent invocation. The envelope carries the "
        "outcome; spans.jsonl is the OpenTelemetry trace the grounding linter checked."
    )

    agent = crate.add(
        SoftwareApplication(
            crate,
            AGENT_BASE + envelope["agent_id"],
            properties={"name": envelope["agent_id"], "version": envelope["agent_version"]},
        )
    )
    # TODO(#26): Process Run Crate has no convention for an accountable role; until one is settled,
    # a role is recorded as a Person whose description says so.
    principal = envelope["acting_for"]
    human = crate.add(
        Person(
            crate,
            principal["principal_id"],
            properties={
                "name": principal["name"],
                "description": (
                    f"The {principal['principal_kind'].replace('_', ' ')} this invocation acted "
                    f"for (assurance: {principal['assurance']})."
                ),
            },
        )
    )
    # An authenticated principal names the issuer that vouched (docs/specs/policy-and-identity.md).
    if issuer_id := principal.get("vouched_by"):
        crate.metadata.extra_terms[VOUCHED_BY] = VOUCHED_BY_IRI
        issuer = crate.add(
            ContextEntity(
                crate,
                issuer_id,
                properties={
                    "@type": "Organization",
                    "name": issuer_id,
                    "description": "The identity provider that vouched for the principal.",
                },
            )
        )
        human[VOUCHED_BY] = issuer
    request_file = crate.add_file(
        request_path, dest_path="request.json", properties={"encodingFormat": "application/json"}
    )
    envelope_file = crate.add_file(
        envelope_path, dest_path="envelope.json", properties={"encodingFormat": "application/json"}
    )
    results = [envelope_file]
    if spans_path is not None and spans_path.exists():
        results.append(
            crate.add_file(
                spans_path,
                dest_path="spans.jsonl",
                properties={"encodingFormat": "application/jsonl"},
            )
        )

    action_props: dict[str, Any] = {
        "name": f"invoke {envelope['agent_id']}",
        "startTime": started_at.isoformat(),
        "endTime": envelope["completed_at"],
        "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
        "description": envelope["outcome"]["statement"],
        "agent": human,
    }
    crate.add_action(
        agent,
        identifier="#" + envelope["invocation_id"],
        object=[request_file],
        result=results,
        properties=action_props,
    )
    _add_model_calls(crate, envelope)
    # The outcome vocabulary is not schema.org; record it as an extra typed entity so a reader of
    # the crate sees the status without opening the envelope.
    crate.add(
        ContextEntity(
            crate,
            "#outcome-" + envelope["invocation_id"],
            properties={
                "@type": "PropertyValue",
                "name": "outcome.status",
                "value": envelope["outcome"]["status"],
            },
        )
    )
    crate.write(out)


def _add_model_calls(crate: ROCrate, envelope: dict[str, Any]) -> None:
    """One `CreateAction` per model call, with the model as instrument and the prompt, named by
    digest and not included, as object (docs/specs/disclosure.md)."""
    models: dict[tuple[str, str], SoftwareApplication] = {}
    for n, call in enumerate(envelope["telemetry"].get("model_calls", []), start=1):
        key = (call["model_provider"], call["model_id"])
        if key not in models:
            models[key] = crate.add(
                SoftwareApplication(
                    crate,
                    f"#model-{call['model_provider']}-{call['model_id']}",
                    properties={
                        "name": call["model_id"],
                        "version": call["model_id"],
                        "provider": call["model_provider"],
                        "description": "A generative language model the agent called.",
                    },
                )
            )
        prompt = crate.add(
            ContextEntity(
                crate,
                f"#prompt-{call['prompt_digest']}",
                properties={
                    "@type": "CreativeWork",
                    "name": "Prompt sent to the model",
                    "sha256": call["prompt_digest"],
                    "description": (
                        "Named by its dd-prompt-json-v1 digest. The prompt is kept with the run, "
                        "not in this crate."
                    ),
                },
            )
        )
        properties: dict[str, Any] = {
            "name": f"call {call['model_id']}",
            "startTime": call["called_at"],
            "actionStatus": {"@id": "http://schema.org/CompletedActionStatus"},
        }
        crate.add_action(
            models[key],
            identifier=f"#{envelope['invocation_id']}-model-call-{n}",
            object=[prompt],
            properties=properties,
        )
