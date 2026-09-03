"""§5.1 tier 1 — local, mechanical profiling with no model involved.

This is the one genuinely complete subsystem at v0.1, and §5.1 says why it comes first: it is
cheap, it is reliable, and R3.4 rests on it entirely.
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
