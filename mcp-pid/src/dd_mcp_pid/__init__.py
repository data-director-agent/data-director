"""A read-only MCP server that resolves persistent identifiers (README.md).

DOIs through DataCite and Crossref, ORCID iDs through ORCID's public API and ROR identifiers
through a pinned ROR dump or ROR's API, each to a small structured record that an MCP client, such
as the Data Director's tool gateway, can hash and cite. Only the identifier is sent upstream.
"""
