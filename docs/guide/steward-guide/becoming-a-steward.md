# Becoming a steward

You are a data steward in a Data Director instance because its institutional profile names you.
No one is a steward by signing in. A person the profile does not name is a researcher.

!!! note "Partly built"
    The profile names the teams, the app knows who is a steward, and a steward can open a project
    the profile's `visibility` allows. Co-approval of a deposit is not built yet
    ([#1306](https://github.com/data-director-agent/data-director/issues/1306)), so `deposit_co_approval` may only be
    `false`; a profile that sets it otherwise is refused when the instance starts.

## Teams

Stewards work in teams, so that a matter is never stuck with one person who is away. The profile's
`stewardship` key lists the teams. The shape is specified in
[Data stewards](../../specs/stewardship.md), invariant 1:

```yaml
stewardship:
  visibility: escalated          # or "scope"; see below
  deposit_co_approval: false     # true: a steward also approves each deposit (Deposit readiness)
  teams:
    - id: library-rdm                        # lower-case words joined by hyphens
      name: Library Research Data Team       # what researchers see
      members:                               # ORCID iDs of the people in the team, as URLs
        - https://orcid.org/0000-0002-1825-0097
      supports: [faculty-of-science, faculty-of-engineering]
      contact: https://example.ac.uk/research-data/contact   # shown when no one can help
      response_time: 3 working days                          # shown to the researcher
```

The profile is the deployment's policy, so a change to it is reviewed like any other change of
policy and is recorded with every run. Ask whoever runs your instance to apply a change
([The policy and the profile](policy-and-profile.md)).

Later, an instance that signs people in through the institution's own identity provider will be
able to map a staff group to a team instead of listing iDs ([#936](https://github.com/data-director-agent/data-director/issues/936)).

## Which projects you can see

`visibility` decides this for the whole instance:

- **`escalated`** (the default): you can open a project only while it has an escalation routed to
  your team, or a pause your team applied.
- **`scope`**: as above, and also any project whose owners chose your team as its support team.
  Until a matter is escalated to your team, you can only read such a project.

No setting lets a steward see every project. Every time you open a project, it is recorded and
shown to the researcher. If you are yourself a member of a project, you act there as a member,
not as its steward.

## What researchers are told

The app tells researchers that a data steward can see their project while an escalation is open,
or while the project is in the team's scope. Your institution's privacy notice should say the same
([Privacy notice](../operations/privacy.md)).

## Administrators

The profile's `administrators` key names the people who manage the instance, each by ORCID iD as
a URL:

```yaml
administrators:
  - https://orcid.org/0000-0002-1825-0097
```

Administrators are the only people a deployed workbench admits. Being an
administrator does not make you a steward, and it gives you no access to anyone's project.
