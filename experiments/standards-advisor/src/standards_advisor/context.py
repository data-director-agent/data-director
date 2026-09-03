"""`RunContext` — LangGraph's `context_schema` for this pipeline.

The clean injection point for everything a node needs but must not own: the registry client, the
prompt library, the ranking weights, the run directory, the agent identity and the model choice.
It is passed to `graph.invoke(context=...)` and reaches every node as `runtime.context`.

Two properties make this the right home for them. It is **never checkpointed**, so it may hold
live objects — an HTTP client, an open database — that have no business being serialised into a
resume record. And it removes any need for module-level state, so two runs with different
registry routes or different weights can proceed side by side without interfering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from standards_advisor.models.common import AgentRef

if TYPE_CHECKING:
    from langchain_core.language_models.chat_models import BaseChatModel

    from standards_advisor.prompting.library import PromptLibrary
    from standards_advisor.provenance.events import ProvenanceHandler
    from standards_advisor.provenance.run_dir import RunDirectory
    from standards_advisor.ranking.weights import RankingConfig
    from standards_advisor.registry.base import RegistryClient


@dataclass(frozen=True)
class RunContext:
    """Static, per-run configuration and collaborators."""

    registry: RegistryClient
    registry_route: str
    prompts: PromptLibrary
    ranking: RankingConfig
    run_dir: RunDirectory
    events: ProvenanceHandler
    agent: AgentRef

    model_id: str
    model_params: dict[str, Any] = field(default_factory=dict)
    """Parameters to send to the model. Empty by default — see `llm.provider`."""

    model_override: BaseChatModel | None = None
    """A pre-built model, used by tests to inject a deterministic fake.

    Injecting the object rather than a provider string is what lets the whole test suite run
    with no API key and with sockets disabled, while the production path still goes through
    `init_chat_model` exactly as a real run does.
    """

    head_rows: int = 500
    """Rows read from the head of a data file (§1.4)."""

    def model(self) -> BaseChatModel:
        """The chat model for this run."""
        if self.model_override is not None:
            return self.model_override
        from standards_advisor.llm.provider import get_model

        return get_model(self.model_id, self.model_params)

    def model_params_as_strings(self) -> dict[str, str]:
        """For the run record, which stores what was sent as strings."""
        return {str(key): str(value) for key, value in self.model_params.items()}
