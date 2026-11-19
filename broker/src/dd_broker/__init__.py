"""The model broker: a separate service that holds people's own model keys, sealed at rest, and
makes model calls for an agent that presents a valid model grant (docs/specs/model-accounts.md).

No agent, and neither the app nor the harness, ever holds a person's key. The broker knows a
person only by a pseudonym, keeps no prompt and no reply, and counts tokens per pseudonym and day.
"""
