"""§5.1 tier 1 — local, mechanical profiling with no model involved.

This is the one genuinely complete subsystem at v0.1, and §5.1 says why it comes first: it is
cheap, it is reliable, and R3.4 rests on it entirely.

Determinism here is a scope boundary, not a bet that mechanical inference generalises to
everything a profile needs. §1.4 permits only column *metadata* — names, inferred types,
counts — to ever reach a model; sample values never do. That constraint is what tier 1 can
cover: file format, header structure, per-column type from a local pattern match. It cannot
cover subject classification from free text or matching a domain's own variable vocabulary —
those need judgement against a controlled term list, which is exactly what tiers 2 and 3
(`nodes/profile.py`) are reserved for, and why they are explicit early returns rather than
mechanical guesses. Model-driven, non-deterministic judgement is not avoided by this design —
it is pushed downstream, past this package, to stages that read tier 1's output rather than raw
file content, so grounding can be checked mechanically after the fact (§5.5) instead of trusted
here.
"""

from standards_advisor.profiling.columns import infer_type, profile_column
from standards_advisor.profiling.files import is_tabular, resolve_format
from standards_advisor.profiling.tabular import TabularHead, read_head

__all__ = [
    "TabularHead",
    "infer_type",
    "is_tabular",
    "profile_column",
    "read_head",
    "resolve_format",
]
