-- Finding the projects a person may read without reading every project's log
-- (docs/specs/storage.md, "Listing"). Each event names the principal whose role it may change
-- (`dd_harness.role_events.names`), in a column of its own, indexed by principal. The index says
-- which logs to read; the access check reads them and decides.

alter table project_events add column names_principal text;

-- A project's creator is its owner (`project_created`); membership events are TODO(#389).
update project_events set names_principal = event -> 'acted_for' ->> 'principal_id'
where event ->> 'event' = 'project_created';

create index project_events_by_principal on project_events (names_principal, project_id, seq)
    where names_principal is not null;
