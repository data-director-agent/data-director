# dd-registry-cache

A local cache in front of a registry that changes slowly, such as FAIRsharing. It answers from a
fresh entry without asking. Once an entry is past its time to live, it asks the registry again,
revalidating with an `ETag` where the registry gives one. When the registry cannot be asked, it
answers from the expired entry and says so.

```python
>>> from dd_registry_cache import Cache, Fresh, Store, Ttl
>>> cache = Cache(Store(path), unavailable=(MyRegistryDown,))
>>> answer = cache.lookup("GET https://example.org/1", Ttl(found=86400, missing=3600), fetch)
>>> answer.origin, answer.checked_at
(<Origin.CACHE: 'cache'>, 1764000000.0)
```

`fetch` is given the stored entry, or None. It returns one of three things:

- `Fresh(body, content_type, etag)` for a new answer;
- `Missing()` when the registry has no such record;
- `NotModified()` when the stored entry is still current, for example after an HTTP 304.

It raises when the registry cannot be asked.

It is contract-free: it imports no other Data Director package and needs only the standard
library, so it can be copied out and published on its own
([System and boundaries](../docs/specs/system.md)). The Data Director SDK's FAIRsharing client
(`dd_sdk.registry.fairsharing`) is built on it.

## Why not an HTTP cache

re3data and FAIRsharing both send `Cache-Control: max-age=0, must-revalidate, private`. A cache
that follows those headers stores nothing it could reuse. The time to live here is therefore the
caller's own decision, made per kind of entry: records, searches, and records not found. A search
sent as a POST, such as FAIRsharing's, is cached under a key the caller makes from its query.

## Answers, in order

1. **A fresh entry** (`Origin.CACHE`). Nothing is asked.
2. **The registry's answer.** A new or changed answer is `Origin.LIVE`. A stored entry the
   registry confirmed current is `Origin.REVALIDATED`, and its clock is reset.
3. **An expired entry** (`Origin.STALE`). This is returned when `fetch` raises one of the
   exceptions the cache was given as `unavailable`.
4. **Otherwise the exception**, raised again.

Errors are never stored. Each answer carries `checked_at`: when the registry last sent or
confirmed it. Each lookup is logged on the `dd_registry_cache` logger, at DEBUG for a hit, a miss
or a revalidation and at INFO for an expired answer.

## Storage and clearing

`Store(path)` keeps one SQLite table in a file, in write-ahead-log mode, which threads of one
process share. `Store()` keeps it in memory for the life of the object. To clear a file, or only
the keys under a prefix:

```bash
dd-registry-cache clear /var/cache/data-director-agent-advisor-standards/fairsharing.sqlite3
```

## Honest limits

- It is one process's cache. Two processes may share a file, but they do not coordinate
  their requests.
- Entries are never evicted, only replaced. A registry's records are few enough for this to be
  acceptable; clear the file if it grows.
- It stores what `fetch` returns, as bytes, and does not parse them.

## Dependencies

None beyond the Python standard library (`sqlite3`).
