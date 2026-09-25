"""The input and payload classes of hello.world, as Pydantic models (ADR-0019).

`schema/hello.yaml` is the source; these models are how the agent builds and reads documents of
its classes. `ClassSchema.of` compares each model with the schema generated from the source, so
a field added to one and not the other fails at import rather than on the wire.
"""

from __future__ import annotations

from typing import Literal

from dd_sdk.contract.models import Derivation, Frozen, Grounded


class Salutation(Frozen):
    """Whom to greet: the input of the `hello.world` template agent."""

    schema_class: Literal["Salutation"] = "Salutation"
    greeted_name: str
    language: str | None = None


class Greeting(Grounded):
    """The payload of the `hello.world` template agent."""

    schema_class: Literal["Greeting"] = "Greeting"
    greeting_text: str
    greeting_derivation: Derivation
