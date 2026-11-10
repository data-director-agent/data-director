-- Listing runs and conversations a page at a time, for the readers allowed to see them
-- (docs/specs/storage.md, "Listing"). What a listing filters on is copied out of the envelope
-- into columns of its own, and indexed in the order a listing reads, newest first.

alter table runs
    add column parent_invocation_id text,
    add column project_id text,
    add column principal_id text;

update runs set
    parent_invocation_id = envelope ->> 'parent_invocation_id',
    project_id = envelope ->> 'project_id',
    principal_id = envelope -> 'acting_for' ->> 'principal_id';

-- A run in no project is read by the principal it acted for; one in a project, by whoever may
-- read the project. Without projects, a run is read by its principal alone.
create index runs_by_principal on runs (principal_id, seq) where project_id is null;
create index runs_by_project on runs (project_id, seq) where project_id is not null;
create index runs_by_principal_alone on runs (principal_id, seq);

-- One row per conversation, written in the transaction that stores each of its turns, so it
-- never disagrees with `runs`: an index of the turns, not a second record of conversations. The
-- first turn's fields are kept as it began the conversation; `last_seq` is the stored place of the
-- latest turn, which orders the listing. Times are kept as the envelope wrote them.
create table conversation_index (
    conversation_id text primary key,
    first_invocation_id text not null references runs (invocation_id),
    project_id text,
    principal_id text,
    agent_id text not null,
    turns integer not null,
    started_at text not null,
    last_seq bigint not null,
    last_completed_at text not null,
    last_status text not null
);
create index conversations_by_activity on conversation_index (last_seq);
create index conversations_by_principal on conversation_index (principal_id, last_seq)
    where project_id is null;
create index conversations_by_project on conversation_index (project_id, last_seq)
    where project_id is not null;
create index conversations_by_principal_alone on conversation_index (principal_id, last_seq);

-- The index of the turns already stored. A turn is a run with a conversation that was not
-- delegated.
with turns as (
    select seq, invocation_id, conversation_id, project_id, principal_id, envelope
    from runs
    where conversation_id is not null and parent_invocation_id is null
),
firsts as (
    select distinct on (conversation_id) * from turns order by conversation_id, seq
),
lasts as (
    select distinct on (conversation_id) * from turns order by conversation_id, seq desc
),
counts as (
    select conversation_id, count(*) as turns from turns group by conversation_id
)
insert into conversation_index (
    conversation_id, first_invocation_id, project_id, principal_id, agent_id, turns,
    started_at, last_seq, last_completed_at, last_status
)
select
    f.conversation_id, f.invocation_id, f.project_id, f.principal_id, f.envelope ->> 'agent_id',
    c.turns, f.envelope ->> 'completed_at', l.seq, l.envelope ->> 'completed_at',
    l.envelope -> 'outcome' ->> 'status'
from firsts f join lasts l using (conversation_id) join counts c using (conversation_id);
