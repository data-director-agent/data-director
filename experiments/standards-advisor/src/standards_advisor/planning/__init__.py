"""Building a profile from documentation rather than from data (§8).

The counterpart of `profiling/`, for the Blueprint's first entry point: a researcher starting a
project, with a README and a draft data dictionary from R5 and no data at all. Where `profiling`
parses values to find out what a column holds, this reads what the researcher has *declared* it
will hold.

That inverts the reliability argument `profiling` rests on. Tier 1 is trustworthy because
parsing a value is mechanical; a declaration is trustworthy because a person who knows the
project wrote it down — `Derivation.RESEARCHER_ANSWER` and
`Derivation.DECLARED_IN_DATA_DICTIONARY` are the strongest signals in that enum, not the
weakest. What a declaration cannot offer is the corroboration a sample gives: nothing here can
notice that a column called `collection_date` will actually be filled in with British-format
dates. So a plan is not a measurement, and the profile keeps them apart — the observation counts
stay `None`, and a declared enumeration is recorded as `permitted_values` rather than as a
distinct-value count.

Both readers are lenient and neither raises. A dictionary or README we cannot read is a fact
about the input, recorded and reported, in the same spirit as `profile._load_metadata`.
"""

from standards_advisor.planning.dictionary import (
    DictionaryFinding,
    ParsedDictionary,
    read_dictionary,
)
from standards_advisor.planning.readme import ParsedReadme, read_readme

__all__ = [
    "DictionaryFinding",
    "ParsedDictionary",
    "ParsedReadme",
    "read_dictionary",
    "read_readme",
]
