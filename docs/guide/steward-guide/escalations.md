# Escalations

An **escalation** hands a matter from a researcher to your team. It is a record in the
researcher's project. Everything that happens to it is kept there and shown to the researcher.

## Where escalations come from

- **The researcher asks.** **Ask a data steward** is available on every project page.
- **An agent offers, and the researcher agrees.** After a referral, an abstention, or when the
  orchestrator sees that the researcher needs a person, the researcher is offered the chance to ask
  you. Nothing is sent until they confirm, after seeing what you will be able to see.

Each escalation tells you its **origin** (the researcher, the policy gate, an agent or the
orchestrator), the researcher's note, and the run that led to it, if any.

## Which team receives it

An escalation goes to the project's **support team**, the team its owners chose. If they have
chosen none, it goes to your instance's only team or, where the profile names several, to the team
the researcher picks when sending; an owner's pick then becomes the project's support team. If you
are a member of the project yourself, you act there as a member: the queue shows the escalation,
and you cannot take it.

## The queue

**Requests**, in the main navigation of anyone the profile names a steward, lists the escalations
routed to your teams, oldest first, with the project, researcher, request, age, state and who has
taken each. By default it shows those still to finish (not taken, taken, or waiting for the
researcher); **Show** filters it by one state. **Projects**, beside **Requests** at the top of the
page, lists the projects you may see (see [Overviews](overviews.md)).

Each row offers the moves open to you on that request, such as **Take**. A move you may not make
is explained in the row, not hidden. The project's name opens the project as its steward (see
[Working in a project](working-in-a-project.md)).

With the keyboard: Tab moves through the filter, the table and each row's project link and
controls; Enter or Space presses a control. A move that needs a note opens a short form in the
row; Enter on its button sends it, and **Cancel** closes it. What each move did is announced.

## What you do with one

| You | It becomes | The researcher sees |
|---|---|---|
| **Take** it | `taken` | "Taken by" your name |
| **Release** it | `open` again, for a colleague | It is back with the team |
| **Ask** the researcher something | `waiting for researcher` | Your question, and "Waiting for you to reply" |
| (The researcher replies) | `taken` | — |
| **Resolve** it, with a note | `resolved` | Your note, and they can disagree or re-open it |
| **Hand back**, with a note | `handed back` | Your note: the matter is theirs to take on |
| **Reassign** it to a colleague | still `taken`, by your colleague | That it was passed to your colleague, by name |
| **Transfer** it to another team, with a note | `open`, for the other team | That it was passed to the other team, and that team's name |

The researcher can **withdraw** an escalation while it is open, taken or waiting, and can
**re-open** one you resolved or handed back. Re-opening keeps its history.

Your profile sets an **expected response time** for each team, and researchers are shown it. If
nobody takes an escalation in that time, the researcher is told, and the escalation is routed again
([#378](https://github.com/data-director-agent/data-director/issues/378)).

## Working as a team

Escalations belong to your team, not to you alone, so that a request is never stuck while you
are away.

- **Reassign** gives a taken escalation to a colleague in your team. Anyone in the team can
  reassign it, not only the steward who took it: if a colleague is away, take over their request
  this way. Choose the colleague from the list; you can add a note for them.
- **Transfer** moves an escalation to another team, with a note saying why it belongs there.
  It goes back to waiting for a steward, the other team is told, and the researcher sees the
  new team's name. A pause you applied stays with your team: lift it when you are done.
- **Cover for a pause.** Anyone in the team that applied a pause can lift it.
- **Conflicts of interest.** If you are a member or owner of the project, you cannot take its
  escalation, pass it on, clear its gates or pause it. The queue shows the moves, says why they
  are not yours to make, and never offers you as the colleague to pass a request to. Co-approving
  a deposit is not built yet
  ([#1306](https://github.com/data-director-agent/data-director/issues/1306)).

With the keyboard: press **Reassign** or **Transfer** in the row, choose the colleague or team
from the list with the arrow keys, Tab to the note, and press Enter on the button to send it.
**Cancel** closes the form. What happened is announced.
