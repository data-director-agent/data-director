"""The Metadata Librarian's evaluation, as an Inspect task: whether the categories it suggests
from a repository's controlled vocabulary are those a curator would choose, whether each cites
the vocabulary record it came from, whether it asks about every value only the researcher can
give and leaves those values null, and whether it stops where it should.

    uv run inspect eval ${DRAFTING} --model none
    uv run inspect eval ${DRAFTING} --model none \\
        -T agents=workbench/agents.yaml        # the deployed services instead

where `DRAFTING` is `agents/advisor-metadata/src/dd_agent_advisor_metadata/evals/drafting.py`.

By default the librarian is built in this process from its own environment variables
(`factory.build`), with the template suggester unless `DD_METADATA_SUGGESTER` asks for a model,
and reached over in-memory A2A. Its conductor serves the subject classifications server
(`mcp-subjects`) in process behind the tool gateway, and grants it to the librarian, so a model
chooses each category from the fields it retrieves there, as in a deployment.

Whoever runs the evaluation is the principal each case is invoked for (`DD_PRINCIPAL_ID`,
`DD_PRINCIPAL_NAME`; docs/specs/policy-and-identity.md). The run records the git revision, the
librarian's version and configuration variables, and hashes of the cases, the rule table and the
suggester's system prompt.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset

from dd_agent_advisor_metadata import scope
from dd_agent_advisor_metadata.agent import MetadataLibrarian
from dd_agent_advisor_metadata.categories import SERVER
from dd_agent_advisor_metadata.evals.scorers import (
    nothing_placed,
    questions_asked,
    subjects_recalled,
    terms_cited,
)
from dd_agent_advisor_metadata.form import SHARES

if TYPE_CHECKING:
    from dd_harness.gateway.config import ToolServer
    from dd_harness.gateway.core import Gateway

AGENT_ID = "advisor.metadata"
HERE = Path(__file__).parent
CASES = HERE / "cases.yaml"
PACKAGE = HERE.parent
CONFIG_VARIABLES = ("DD_METADATA_SUGGESTER", "DD_MODEL_PROVIDER", "DD_MODEL_ID")
# What the inventory tool would say of every case's files: a case gives only what a curator reads.
INVENTORY = {
    "schema_class": "FileInventory",
    "inventory_tool": "dd-inventory",
    "inventory_tool_version": "0.1.0-alpha",
    "inventory_made_at": "2026-11-01T00:00:00+00:00",
}


def _file(row: list[Any]) -> dict[str, Any]:
    """One inventory file from a case's `[path, media type, size, {fields}]`. Its hash is that of
    its path, since a case has no bytes."""
    path, media_type, size, *rest = row
    extra = rest[0] if rest else {}
    entry: dict[str, Any] = {
        "file_path": path,
        "file_size": size,
        "file_sha256": hashlib.sha256(path.encode()).hexdigest(),
        "file_media_type": media_type,
        "file_identified_by": "extension",
    }
    if "fields" in extra:
        entry["file_fields"] = [{"name": n, "field_type": t} for n, t in extra["fields"]]
    return entry


def _researcher(keywords: list[str]) -> dict[str, Any]:
    return {
        "orcid_id": "https://orcid.org/0000-0002-1825-0097",
        "record_retrieved_at": "2026-11-01T00:00:00Z",
        "record_source": "https://pub.orcid.org/v3.0/record",
        "keywords": keywords,
    }


def draft_request(given: dict[str, Any], requirements: dict[str, Any]) -> dict[str, Any]:
    """A case's `input` as the `DraftRequest` the librarian is given (`cases.yaml`)."""
    asked: dict[str, Any] = {
        "schema_class": "DraftRequest",
        "document_kind": given.get("document_kind", "metadata_record"),
        "inventory": {**INVENTORY, "inventory_files": [_file(f) for f in given["files"]]},
    }
    if not given.get("no_repository"):
        asked["requirements"] = {
            **requirements,
            "conforms_to": given.get("conforms_to", requirements["conforms_to"]),
        }
    if given.get("keywords"):
        asked["researchers"] = [_researcher(given["keywords"])]
    return asked


def load_cases(path: Path = CASES) -> list[dict[str, Any]]:
    """The cases, each with its input as a `DraftRequest` document."""
    table = yaml.safe_load(path.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = table["cases"]
    for case in cases:
        case["input"] = draft_request(case["input"], table["requirements"])
    return cases


def dataset(cases: list[dict[str, Any]]) -> MemoryDataset:
    from workbench.evaluation import case_dataset

    return case_dataset(cases, ("expect",), "metadata-drafting")


def identity(agents: str | None) -> dict[str, Any]:
    from workbench.evaluation import configuration, sha256_of, task_identity

    hashes = {
        "cases_sha256": sha256_of(CASES),
        "definitions_sha256": {s.standard_id: s.definition.sha256 for s in scope.standards()},
        "shares_sha256": sha256_of(SHARES),
        "system_prompt_sha256": sha256_of(PACKAGE / "suggest_prompt.md"),
    }
    return task_identity(
        AGENT_ID,
        HERE,
        hashes,
        agents,
        lambda: {
            "spec_version": MetadataLibrarian.spec.version,
            "configuration": configuration(CONFIG_VARIABLES),
        },
    )


def librarian() -> MetadataLibrarian:
    """The librarian evaluated in this process: as its own configuration builds it, except that
    the evaluation calls no model unless `DD_METADATA_SUGGESTER` asks for one (invariant 1 of the
    evaluation spec), although the librarian's own default is `model`."""
    from dd_agent_advisor_metadata.factory import build

    return build({"DD_METADATA_SUGGESTER": "template", **os.environ})


def subjects_server() -> ToolServer:
    """The subject classifications server as a deployment lists it (`mcp-subjects`), pinned to
    the tools it lists."""
    from dd_harness.gateway.config import ToolServer, tools_digest
    from dd_mcp_subjects.tools import Tools
    from dd_sdk.evidence import DOCUMENT_CANONICALISATION

    return ToolServer(
        name=SERVER,
        url="http://127.0.0.1:8314/subjects/mcp",
        id_field="id",
        canonicalisation=DOCUMENT_CANONICALISATION,
        tools_sha256=tools_digest(
            t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in Tools().listed
        ),
    )


def subjects_gateway() -> Gateway:
    """A tool gateway over the subject classifications server, served in this process."""
    from dd_harness.testing.tools import fake_gateway
    from dd_mcp_subjects.server import server
    from dd_mcp_subjects.tools import Tools

    return fake_gateway(subjects_server(), serve=lambda _server: server(Tools()))


@task
def metadata_drafting(agents: str | None = None) -> Task:
    from workbench.config import settings_from_env
    from workbench.evaluation import (
        grounding_passed,
        invoke_agent,
        one_conductor,
        outcome_matches,
        stopped_correctly,
    )

    agent = None if agents else librarian()
    return Task(
        dataset=dataset(load_cases()),
        solver=invoke_agent(
            one_conductor(
                lambda: agent,
                agents,
                "dd-eval-metadata-",
                gateway=subjects_gateway,
                tool_grants={AGENT_ID: [SERVER]},
            ),
            AGENT_ID,
            settings_from_env().principal(),
        ),
        scorer=[
            outcome_matches(),
            stopped_correctly(),
            grounding_passed(),
            subjects_recalled(),
            terms_cited(),
            questions_asked(),
            nothing_placed(),
        ],
        metadata={"identity": identity(agents)},
    )
