"""The model seam's router: which provider and model serve each model an agent's card declares
(docs/specs/model-accounts.md, invariant 15 and The route; issue #843).

An agent that calls through the model broker is given a `RoutedModel` by
`dd_sdk.model_provider.configured_model`. Before the first call a run makes to a declared model, it
asks the broker's `POST /route` which provider and model serve it, sending the declared provider
and model with the agent's broker credential and the run's model grant. The broker answers from the
grant and the person's account alone. Every call the run makes to that model then goes to the
answer: through the declared model's own adapter when the answer is the declared model, or through
an adapter built for the provider and model the answer names, in which case each call notes the
declared model (`dd_sdk.model_account.routed`) so its record names it.

The card is unchanged: a `RoutedModel` reports the declared provider, model and hosting. An agent's
own code never chooses the route, and a client it calls outside the model seam is not routed.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, Literal

import httpx

from dd_sdk import model_account
from dd_sdk.model import Model, ModelCallError, ModelRequest, ModelResponse, current_grant
from dd_sdk.model_grant import HEADER_GRANT, HEADER_REASON

ROUTE_PATH = "/route"
# How long to wait for the broker's answer, in seconds.
ROUTE_TIMEOUT_S = 30.0
# How many runs' routes a model keeps at once. A run is known by its grant, which is new for every
# invocation, so this bounds memory, not correctness: an evicted run asks again.
_RUNS_KEPT = 256

# Builds the adapter for a provider and model the broker named.
type Builder = Callable[[str, str], Model]


def http_client() -> httpx.Client:
    """The client the router asks the broker with. Tests replace it."""
    return httpx.Client(timeout=ROUTE_TIMEOUT_S)


class RouteRefusedError(Exception):
    """The broker refused to answer a route. The answer is on `response`, so that
    `dd_sdk.model_account.refusal` reads its `X-DD-Reason` as it reads a refused call's."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(
            f"the model broker refused the route: {response.headers.get(HEADER_REASON, '')}"
        )
        self.response = response


class RoutedModel:
    """A declared model, routed through the broker to whatever serves it for this run."""

    def __init__(
        self,
        declared: Model,
        *,
        broker_url: str,
        credential: str,
        build: Builder,
    ) -> None:
        self._declared = declared
        self._route_url = broker_url.rstrip("/") + ROUTE_PATH
        self._credential = credential
        self._build = build
        self.provider: str = declared.provider
        self.model_id: str = declared.model_id
        self.hosting: Literal["hosted", "local"] = declared.hosting
        self.tool_use: bool = bool(getattr(declared, "tool_use", False))
        self._lock = threading.Lock()
        # The answer for each run, by its grant.
        self._routes: OrderedDict[str, tuple[str, str]] = OrderedDict()
        # The adapter for each provider and model the broker has named.
        self._served: dict[tuple[str, str], Model] = {}

    def __repr__(self) -> str:
        return f"RoutedModel({self.provider!r}, {self.model_id!r})"

    @property
    def declared(self) -> Model:
        """The adapter for the model the card declares."""
        return self._declared

    def send(self, request: ModelRequest) -> ModelResponse:
        target, declared = self._target()
        model_account.routed(declared)
        return target.send(request)

    def _target(self) -> tuple[Model, str | None]:
        """The adapter this run's calls go to, and the declared model if it was routed."""
        grant = current_grant()
        if grant is None:
            # No grant, no route: the call goes as declared, and the broker refuses it.
            return self._declared, None
        provider, model = self._route(grant)
        if (provider, model) == (self.provider, self.model_id):
            return self._declared, None
        with self._lock:
            served = self._served.get((provider, model))
            if served is None:
                served = self._served[(provider, model)] = self._build(provider, model)
        return served, self.model_id

    def _route(self, grant: str) -> tuple[str, str]:
        with self._lock:
            if (known := self._routes.get(grant)) is not None:
                self._routes.move_to_end(grant)
                return known
        answer = self._ask(grant)
        with self._lock:
            self._routes[grant] = answer
            while len(self._routes) > _RUNS_KEPT:
                self._routes.popitem(last=False)
        return answer

    def _ask(self, grant: str) -> tuple[str, str]:
        try:
            with http_client() as client:
                response = client.post(
                    self._route_url,
                    headers={"x-api-key": self._credential, HEADER_GRANT: grant},
                    json={"provider": self.provider, "model": self.model_id},
                )
        except httpx.HTTPError as exc:
            raise ModelCallError(f"the model broker could not be reached: {exc}") from None
        if response.status_code != 200:
            raise ModelCallError(
                f"the model broker answered {response.status_code} to a route"
            ) from RouteRefusedError(response)
        return _answer(response.json() if _is_json(response) else None)


def _is_json(response: httpx.Response) -> bool:
    try:
        response.json()
    except ValueError:
        return False
    return True


def _answer(document: Any) -> tuple[str, str]:
    if (
        isinstance(document, dict)
        and isinstance(document.get("provider"), str)
        and isinstance(document.get("model"), str)
        and document["provider"]
        and document["model"]
    ):
        return document["provider"], document["model"]
    raise ModelCallError("the model broker's route is not a provider and a model")
