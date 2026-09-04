"""The intake question set (§8) — what `elicit` asks, loaded from a versioned file.

Configuration rather than a prompt, and the distinction is not bureaucratic: no model is
involved. The questions are fixed text put to a person, so they belong beside `ranking.v1.toml`
rather than in `prompts/`, and they are versioned by filename and hashed for the same reason —
a run record from six months ago must still resolve to the questions actually asked (R10).

There is a second, harder reason the set is fixed. Anything the `elicit` node computes *before*
it pauses runs again when the graph resumes, because LangGraph re-runs a node from the top. A
model-generated question would therefore be generated twice, from a non-deterministic call, and
the researcher could be shown one set of questions and have their answers validated against
another.
"""

from standards_advisor.intake.config import IntakeConfig, load_intake_config

__all__ = ["IntakeConfig", "load_intake_config"]
