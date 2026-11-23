"""Data use conditions from the GA4GH Data Use Ontology (DUO).

DUO gives standard terms for the conditions under which data may be used, as consent forms and
data access committees state them: permissions (general research use, health or medical research)
and modifiers (ethics approval required, non-commercial use only). `lookup` turns an identifier or
shorthand into the term of a pinned DUO release, held as data with its source and licence, so that
naming a condition needs no network and sends nothing anywhere.
"""

from dd_duo.duo import PinError, Release, Term, lookup, release, terms

__all__ = ["PinError", "Release", "Term", "lookup", "release", "terms"]
