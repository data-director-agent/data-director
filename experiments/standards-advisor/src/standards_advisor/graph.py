"""The pipeline as a LangGraph `StateGraph`.

Six nodes, one straight line, **no conditional edges**. That is a decision rather than a
simplification, and it is the structural expression of R3.6: abstention is *output*, not control
flow. A stage that finds nothing still runs the next one, and `assemble` writes the
`nothing_found` entries. Branching on emptiness would put abstention on an error path — the one
thing §5.5 says it must not be — and would make the six stage boundaries conditional, which both
the coverage check and §6.3's one-activity-per-stage rely on being unconditional.

`StateGraph` rather than an LCEL `a | b | c` chain: LCEL has no state schema, no per-stage
checkpointing and no resume, which is most of what this pipeline needs. And not `create_agent`:
a model-driven loop would reintroduce exactly the nondeterminism the design is built to avoid.
When §5.6's model-directed retrieval arrives it belongs in a *bounded internal loop* inside
`retrieve`, not as a graph cycle, so that a "stage" keeps its meaning in the provenance record.
"""

from __future__ import annotations

from itertools import pairwise
from typing import TYPE_CHECKING, Any

from langgraph.graph import END, START, StateGraph

from standards_advisor.context import RunContext
from standards_advisor.models.common import StageName
from standards_advisor.nodes import (
    assemble_node,
    check_node,
    explain_node,
    profile_node,
    rank_node,
    retrieve_node,
)
from standards_advisor.state import PipelineState

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver
    from langgraph.graph.state import CompiledStateGraph

#: Stage order, and therefore edge order. `graph.get_state_history()` yields one boundary per
#: entry, which is what §5's "each stage saves its result" comes down to.
PIPELINE_ORDER: tuple[StageName, ...] = (
    StageName.PROFILE,
    StageName.RETRIEVE,
    StageName.RANK,
    StageName.EXPLAIN,
    StageName.CHECK,
    StageName.ASSEMBLE,
)


def build_graph(
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> CompiledStateGraph[PipelineState, RunContext, PipelineState, PipelineState]:
    """Assemble and compile the pipeline.

    The nodes are registered by explicit calls rather than by looping over a table of
    callables. It is more lines, but each node's real signature is then checked against
    LangGraph's node protocol — routing them through a `Callable[...]` alias erases the
    parameter names the protocol matches on, so the loop version type-checks nothing.
    """
    builder: StateGraph[PipelineState, RunContext, PipelineState, PipelineState] = StateGraph(
        PipelineState, context_schema=RunContext
    )

    builder.add_node(StageName.PROFILE.value, profile_node)
    builder.add_node(StageName.RETRIEVE.value, retrieve_node)
    builder.add_node(StageName.RANK.value, rank_node)
    builder.add_node(StageName.EXPLAIN.value, explain_node)
    builder.add_node(StageName.CHECK.value, check_node)
    builder.add_node(StageName.ASSEMBLE.value, assemble_node)

    builder.add_edge(START, PIPELINE_ORDER[0].value)
    for current, following in pairwise(PIPELINE_ORDER):
        builder.add_edge(current.value, following.value)
    builder.add_edge(PIPELINE_ORDER[-1].value, END)

    return builder.compile(checkpointer=checkpointer)
