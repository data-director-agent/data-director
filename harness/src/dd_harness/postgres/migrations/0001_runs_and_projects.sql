-- The run storage and the project log (docs/specs/storage.md). Documents are kept as `json`, not
-- `jsonb`, so each is read back as it was given: `jsonb` refuses the escaped NUL a researcher's
-- text may hold. What is looked up is kept in a column of its own and indexed.

-- Runs, in the order stored: `seq` is assigned as each is stored (invariant 3).
create table runs (
    seq bigint generated always as identity primary key,
    invocation_id text not null unique,
    conversation_id text,
    envelope json not null,
    request json,
    prompts json
);
create index runs_by_conversation on runs (conversation_id, seq)
    where conversation_id is not null;

-- Each class schema a run was checked against, once, under its digest (invariant 6).
create table run_schemas (
    digest text primary key,
    schema json not null
);

-- Everything else a run keeps, written once (invariant 5).
create table run_artifacts (
    invocation_id text not null references runs (invocation_id),
    name text not null,
    data bytea not null,
    primary key (invocation_id, name)
);

-- A project's row is what its exclusive section locks (invariant 10).
create table projects (
    project_id text primary key,
    created bigint generated always as identity unique
);

-- Each project's events, in the order appended (invariant 9).
create table project_events (
    seq bigint generated always as identity primary key,
    project_id text not null references projects (project_id),
    event json not null,
    started_conversation text
);
create index project_events_by_project on project_events (project_id, seq);
create index project_events_by_conversation on project_events (started_conversation)
    where started_conversation is not null;

-- Content an event added, kept once by digest.
create table project_blobs (
    project_id text not null references projects (project_id),
    digest text not null,
    content bytea not null,
    primary key (project_id, digest)
);
