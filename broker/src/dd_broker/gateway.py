"""Where the deployment's calls go when the operator runs a gateway
(`DD_BROKER_DEPLOYMENT_BASE_URL`, normally the LiteLLM gateway in deploy/llm-gateway).

Anthropic's calls go to the gateway's `/v1/messages`, every other provider's to its
`/v1/chat/completions`. Each call is tagged with the agent the grant names, in the header LiteLLM
takes request tags from, so that the gateway's spend reports show each agent's calls although all
arrive on the broker's one key (deploy/llm-gateway/README.md, "With the model broker"). The tag
names the agent, never the person: who made a call is in the broker's own usage store, by
pseudonym. Only the deployment's calls come here; a person's own account never does.
"""

from __future__ import annotations

from dd_broker import anthropic, chat_completions
from dd_broker.guard import Target

# The header in which the LiteLLM gateway takes a request's tags, which its spend reports group by.
TAGS_HEADER = "x-litellm-tags"


def target(base_url: str, provider: str, agent: str) -> Target:
    """The gateway at `base_url`, for a call to `provider` made by `agent`."""
    url = base_url if provider == anthropic.PROVIDER else base_url + chat_completions.GATEWAY_PATH
    return Target(url=url, extra=((TAGS_HEADER, f"agent:{agent}"),))
