"""Journals by ISSN and title, from a pinned OpenAlex snapshot built at install.

The ISSN International Centre assigns each serial its ISSNs and a linking ISSN (ISSN-L), but its
bulk data are not open. OpenAlex (CC0) lists about 170,000 journals with their ISSN-L, other
ISSNs, publisher and open access status. `dd-journals fetch` builds a registry of them from one
pinned snapshot, checked by SHA-256, so that looking a journal up needs no network and sends
nothing anywhere. Each journal links to its ISSN Portal record as the authoritative reference.
"""

from dd_journals.issn import normal_issn, valid_issn
from dd_journals.records import Journal
from dd_journals.registry import PinError, Registry, fold
from dd_journals.snapshot import Pin, registry

__all__ = [
    "Journal",
    "Pin",
    "PinError",
    "Registry",
    "fold",
    "normal_issn",
    "registry",
    "valid_issn",
]
