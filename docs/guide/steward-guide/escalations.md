# Escalations

An **escalation** hands a matter from a researcher to your team. It is a record in the
researcher's project. Everything that happens to it is kept there and shown to the researcher.

!!! note "Not built yet"
    Escalations, the queue and the controls below are specified in
    [Data stewards](../../specs/stewardship.md) and not yet built ([#373](https://github.com/data-director-agent/data-director/issues/373),
    [#375](https://github.com/data-director-agent/data-director/issues/375), [#376](https://github.com/data-director-agent/data-director/issues/376)).

## Where escalations come from

- **The researcher asks.** **Ask a data steward** is available on every project page.
- **An agent offers, and the researcher agrees.** After a referral, an abstention, or when the
  orchestrator sees that the researcher needs a person, the researcher is offered the chance to ask
  you. Nothing is sent until they confirm, after seeing what you will be able to see.

Each escalation tells you its **origin** (the researcher, the policy gate, an agent or the
orchestrator), the researcher's note, and the run that led to it, if any.

## The queue

**Steward queue** lists the escalations routed to your team, oldest first, with the project,
researcher, reason, age, state and who has taken each. You can filter it by state.

## What you do with one

| You | It becomes | The researcher sees |
|---|---|---|
| **Take** it | `taken` | "Taken by" your name |
| **Release** it | `open` again, for a colleague | It is back with the team |
| **Ask** the researcher something | `waiting for researcher` | Your question, and "Waiting for you to reply" |
| (The researcher replies) | `taken` | — |
| **Resolve** it, with a note | `resolved` | Your note, and they can disagree or re-open it |
| **Hand back**, with a note | `handed back` | Your note: the matter is theirs to take on |

The researcher can **withdraw** an escalation while it is open, taken or waiting, and can
**re-open** one you resolved or handed back. Re-opening keeps its history.

Your profile sets an **expected response time** for each team, and researchers are shown it. If
nobody takes an escalation in that time, the researcher is told, and the escalation is routed again
([#378](https://github.com/data-director-agent/data-director/issues/378)).

## Working as a team

!!! note "Not built yet"
    Reassigning and transferring escalations, and the rules for conflicts of interest, are
    [#1308](https://github.com/data-director-agent/data-director/issues/1308).

- **Reassign** gives a taken escalation to a named colleague in your team.
- **Transfer** moves it to another team, with a note. The researcher sees the new team.
- **Conflicts of interest.** If you are a member or owner of the project, you cannot take its
  escalation, clear its gates, pause it or co-approve its deposit. The queue says why.
