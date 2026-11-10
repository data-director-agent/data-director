-- Finding the projects a principal may read without reading every project's log
-- (docs/specs/storage.md, "Listing"). A row for each principal an event of a project names
-- (`dd_harness.listing.principals_named`), written in the transaction that appends the event, so
-- it never disagrees with `project_events`: an index of the log, not a record of membership.
-- Who may read a project is still judged from its log (`dd_harness.project_access`).

create table project_principals (
    principal_id text not null,
    project_id text not null references projects (project_id),
    primary key (principal_id, project_id)
);

-- The principals named by the events already stored: whom each acted for.
insert into project_principals (principal_id, project_id)
select distinct event -> 'acted_for' ->> 'principal_id', project_id
from project_events
where event -> 'acted_for' ->> 'principal_id' is not null;
