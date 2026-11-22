"""What agents that read a registry share: retrieval types, the snapshot tokeniser, the
pinned-download pipeline, FAIRsharing's API with its local cache, and which copy answered for
each record. Each agent keeps its own records, protocols and ranking; see each module."""

from dd_sdk.registry.retrieve import Hit, Query, RegistryUnavailable, SnapshotRef

__all__ = ["Hit", "Query", "RegistryUnavailable", "SnapshotRef"]
