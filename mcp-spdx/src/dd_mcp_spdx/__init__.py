"""A read-only MCP server for a pinned release of the SPDX licence list (README.md).

Looks up a licence by its SPDX identifier in a copy of one release packaged with the server,
answering small structured records an MCP client, such as the Data Director's tool gateway, can
hash and cite. It reaches no network.
"""
