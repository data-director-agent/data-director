"""File formats described from their PRONOM records.

PRONOM, The National Archives' technical registry, gives each file format an identifier (a PUID,
such as `fmt/353`) and a record: the format's name, version, media types and file extensions.
Format identification tools such as DROID, fido and Siegfried report PUIDs; `lookup` turns one
into the record of a pinned PRONOM release, held as data with its source and licence, so that
naming a format needs no network and sends nothing anywhere.
"""

from dd_formats.pronom import FormatRecord, Release, lookup, records, release

__all__ = ["FormatRecord", "Release", "lookup", "records", "release"]
