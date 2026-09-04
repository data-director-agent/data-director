"""Process Run Crate for one invocation (R10), written with ro-crate-py.

One `CreateAction` per invocation: the agent is the instrument, the request the object, the
envelope and the span file the results. Profile: https://w3id.org/ro/wfrun/process/0.5.
This module is the only importer of `rocrate` (ADR-0006).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from rocrate.model import ContextEntity, SoftwareApplication
from rocrate.rocrate import ROCrate

PROCESS_RUN_CRATE = "https://w3id.org/ro/wfrun/process/0.5"
AGENT_BASE = "https://w3id.org/data-director/agents/"


def write_process_run_crate(
    run_dir: Path,
    envelope: dict[str, Any],
    request_path: Path,
    envelope_path: Path,
    spans_path: Path | None,
    started_at: datetime,
) -> Path:
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
    }
    crate.add_action(
        agent,
        identifier="#" + envelope["invocation_id"],
        object=[request_file],
        result=results,
        properties=action_props,
    )
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
    out = run_dir / "crate"
    crate.write(out)
    return out
