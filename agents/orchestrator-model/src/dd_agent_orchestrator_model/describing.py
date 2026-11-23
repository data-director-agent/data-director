"""The orchestrator's `propose_data_description` tool (`agent.py`), which runs nothing: it proposes
a `data_description` project fact from what the researcher said, for a person to confirm on the
project page (docs/specs/orchestration.md, docs/specs/projects.md, invariant 28).

What the data are and how they are collected is said in a conversation, and a conversation is
not read by any other agent. Once a person confirms the proposal it is part of the project's
record, and the conductor gives it to every drafter and orchestrator in the project
(`project_decisions`), whichever conversation they run in. Until then it is only a proposal, and
no agent is given it. Each value is the researcher's own words, never the model's inference; the
words it rests on are kept on `proposed_because`, which only the person deciding is shown.
"""

from __future__ import annotations

from collections.abc import Sequence

from dd_sdk.contract.facts import PLAN_SUBJECT, FactKind, ProjectFact
from dd_sdk.model import ToolCall, ToolResult, ToolSpec

DESCRIBE_TOOL = "propose_data_description"

# What each value the tool takes says, by its `ProjectFact` slot.
_VALUES = {
    "data_collected": (
        "What data the project collects, produces or reuses, and of which types, such as "
        "'interview recordings and transcripts, and survey responses'."
    ),
    "data_collection_method": "How the data are collected or produced.",
    "data_formats": "The file formats the data are or will be kept in.",
    "data_volume": "How much data the project expects, with its unit, such as '20 GB'.",
    "data_reused": "Which existing data the project reuses, and how.",
}
# The longest value taken, in characters: a few sentences, not a document.
MAX_VALUE = 1000

DESCRIBE_TOOL_DEFINITION = ToolSpec(
    name=DESCRIBE_TOOL,
    description=(
        "Propose a description of the project's data for the researcher to confirm on the project "
        "page, so that every agent in the project, such as the one drafting their Data "
        "Management Plan, is given it in later conversations too. Call it once the researcher "
        "has told you what data they collect or produce, and call it again with every value "
        "when they add to or correct it. Give each value in the researcher's own words, from "
        "this conversation only: leave out anything they have not said, and never infer a "
        "type, method, format or volume. It runs nothing and your turn goes on; tell them the "
        "description waits for them to confirm on the project page."
    ),
    input_schema={
        "type": "object",
        "properties": {
            **{
                slot: {"type": "string", "maxLength": MAX_VALUE, "description": said}
                for slot, said in _VALUES.items()
            },
            "quote": {
                "type": "string",
                "maxLength": MAX_VALUE,
                "description": "The researcher's words the description rests on, quoted.",
            },
        },
        "required": ["data_collected", "quote"],
        "additionalProperties": False,
    },
)


def description_of(call: ToolCall) -> tuple[ProjectFact | None, ToolResult]:
    """The `data_description` fact a `propose_data_description` call proposes, and the tool
    result to send back: None and an error when what it gives is not a description."""
    given = {
        slot: value.strip()
        for slot in _VALUES
        if isinstance(value := call.input.get(slot), str) and value.strip()
    }
    quote = call.input.get("quote")
    try:
        fact = ProjectFact(
            fact_kind=FactKind.DATA_DESCRIPTION,
            fact_subject=PLAN_SUBJECT,
            proposed_because=quote.strip() if isinstance(quote, str) and quote.strip() else None,
            **given,
        )
    except ValueError:  # pydantic's ValidationError
        return None, ToolResult(
            call.id,
            "Not proposed: say what data the project collects in data_collected.",
            is_error=True,
        )
    if any(len(v) > MAX_VALUE for v in given.values()):
        return None, ToolResult(
            call.id, f"Not proposed: keep each value under {MAX_VALUE} characters.", is_error=True
        )
    return fact, ToolResult(
        call.id,
        "Proposed. Carry on with your reply; tell the researcher it waits for them to confirm "
        "on the project page.",
        is_error=False,
    )


def described(
    calls: Sequence[ToolCall], before: ProjectFact | None
) -> tuple[ProjectFact | None, dict[str, ToolResult]]:
    """The last description a turn's `propose_data_description` calls propose, else `before`,
    and the result for each call."""
    answered: dict[str, ToolResult] = {}
    for made in (c for c in calls if c.name == DESCRIBE_TOOL):
        fact, answered[made.id] = description_of(made)
        before = fact or before
    return before, answered
