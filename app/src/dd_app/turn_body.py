"""What one turn of a conversation gives, and the checks on the body that sends it
(`POST /api/conversations/{id}/turns`, and its stream's `forwardedProps`; docs/specs/app.md)."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from starlette.responses import Response

from dd_app.problems import refused
from dd_sdk.contract.models import ReplyAnswers

# Why a turn's `documentation` is refused for its shape.
DOCUMENTATION_REFUSAL = (
    "`documentation` must be an object giving the document's `name`, `media_type` and `text`, "
    "or for a Word document or PDF its `name`, `media_type` and the file as base64 `data`, "
    "as strings."
)


@dataclass(frozen=True)
class AttachedDocument:
    """A supporting document a turn attaches: its file name, media type and text, or, for a Word
    document or PDF, the file itself, whose text the server reads (`read_document_file`)."""

    name: str
    media_type: str
    text: str = ""
    data: bytes | None = None


@dataclass(frozen=True)
class Turn:
    """What one turn gives: the agent it goes to, the message, the turn it follows (None for the
    first), and what it may attach or answer."""

    agent_id: str
    message_text: str
    follows: str | None
    inventory: Mapping[str, Any] | None = None
    answer: ReplyAnswers | None = None
    documentation: AttachedDocument | None = None


def _documentation(attached: Any) -> AttachedDocument | Response | None:
    """A turn's `documentation`, checked, or the `400` problem that refuses it."""
    if attached is None:
        return None
    shapes = ({"name", "media_type", "text"}, {"name", "media_type", "data"})
    if not (
        isinstance(attached, dict)
        and set(attached) in shapes
        and all(isinstance(value, str) for value in attached.values())
    ):
        return refused(DOCUMENTATION_REFUSAL)
    if "data" not in attached:
        return AttachedDocument(**attached)
    data = decoded(attached["data"])
    if data is None:
        return refused("`documentation.data` must be the file, encoded as base64.")
    return AttachedDocument(attached["name"], attached["media_type"], data=data)


def decoded(data: str) -> bytes | None:
    """The bytes `data` encodes as base64, or None if it is not base64."""
    try:
        return base64.b64decode(data, validate=True)
    except binascii.Error:
        return None


def _reply_answers(given: Any) -> ReplyAnswers | Response | None:
    """A turn's `reply_answers`, checked, or the `400` problem that refuses it."""
    if given is None:
        return None
    try:
        return ReplyAnswers.model_validate(given)
    except ValueError:
        return refused(
            "`reply_answers` must name the turn it answers (`answer_to`) and give "
            "`given_answers`: for each question answered, its `answered_key`, the "
            "`answer_values` chosen and optionally `answer_words`."
        )


def _turn_shape(body: Any) -> Response | None:
    """The `400` problem that refuses a turn's body for its shape, or None: it must be an object,
    give no history and name only the fields a turn takes."""
    if not isinstance(body, dict):
        return refused("The body must be an object with `agent_id`, `message_text` and `follows`.")
    if "history" in body:
        return refused("A turn may not give a history: the server builds it from the stored turns.")
    allowed = {
        "agent_id",
        "message_text",
        "follows",
        "inventory",
        "documentation",
        "reply_answers",
    }
    if extra := sorted(set(body) - allowed):
        return refused(
            "A turn takes only `agent_id`, `message_text`, `follows`, `inventory`, "
            f"`documentation` and `reply_answers`, not {extra}."
        )
    return None


def _turn_fields(body: dict[str, Any]) -> Response | None:
    """The `400` problem that refuses a turn's body for its plain fields, or None: `agent_id` and
    `message_text` are strings, `follows` is given as a string or null, and `inventory` is an
    object if given."""
    agent_id, message_text = body.get("agent_id"), body.get("message_text")
    if not isinstance(agent_id, str) or not isinstance(message_text, str):
        return refused("The body must name `agent_id` and give `message_text`, as strings.")
    follows = body.get("follows")
    if "follows" not in body or not (follows is None or isinstance(follows, str)):
        return refused(
            "The body must give `follows`: the `invocation_id` of the turn this one follows, "
            "or null for the first turn."
        )
    inventory = body.get("inventory")
    if not (inventory is None or isinstance(inventory, dict)):
        return refused("`inventory` must be the object `dd-inventory` wrote.")
    return None


def parse_turn(body: Any) -> Turn | Response:
    """A turn's body, checked, or the `400` problem that refuses it. The turn's stream takes the
    same body as its `forwardedProps`."""
    if (wrong := _turn_shape(body)) is not None or (wrong := _turn_fields(body)) is not None:
        return wrong
    agent_id, message_text = body["agent_id"], body["message_text"]
    follows, inventory = body["follows"], body.get("inventory")
    documentation = _documentation(body.get("documentation"))
    if isinstance(documentation, Response):
        return documentation
    if not message_text.strip() and inventory is None and documentation is None:
        return refused("The message is empty.")
    answer = _reply_answers(body.get("reply_answers"))
    if isinstance(answer, Response):
        return answer
    return Turn(agent_id, message_text, follows, inventory, answer, documentation)
