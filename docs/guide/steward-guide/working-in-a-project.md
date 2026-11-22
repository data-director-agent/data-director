# Working in a project

While an escalation is open, or while a project is in your team's scope, you can open the
researcher's project and help in it.

!!! note "Partly built"
    The server checks and records opening a project as a steward, writing to the researcher,
    proposing an edit, running an agent, clearing or refusing a stopped step, and pausing
    ([#374](https://github.com/data-director-agent/data-director/issues/374)). The screens described here are
    [#376](https://github.com/data-director-agent/data-director/issues/376). Clearing a step records your decision but does
    not yet resume it ([#16](https://github.com/data-director-agent/data-director/issues/16)), and the credit in the deposit
    package's provenance is [#1481](https://github.com/data-director-agent/data-director/issues/1481).

## What you see

You see the same project view the researcher sees: its documents, facts, inventory, conversations,
runs and deposit tab. A banner you cannot dismiss reads **Viewing as a data steward**, with the
researcher's name and the escalation, which sits beside the project with the history and your own
notes.

Opening the project is recorded. The researcher sees "*Name* viewed this project on *date*".
Repeated looks on the same day are recorded once.

## What you can do

The app shows only the actions open to you, and explains any it refuses.

| Action | What happens | Who decides |
|---|---|---|
| **Write to the researcher** | Your message appears in the project's conversation with your name, never as an agent's. | — |
| **Propose an edit** | Your edit to a document becomes a new *proposed* version, marked as yours. | The researcher approves or rejects it. |
| **Run an agent** | The same controls the researcher has, labelled as run by you. The run acts for you, and its drafts are proposed versions. | The researcher decides on the drafts. |
| **Clear or refuse a stopped step** | For a step policy referred to a steward, you clear or refuse it with a reason. | You decide the exception; the researcher still approves the result. |
| **Pause the project** | See below. | Your team lifts it. |
| **Resolve or hand back** the escalation | With a note to the researcher. | — |

You cannot decide a project fact, approve or reject a document version, approve a deposit, change
who is a member, or delete the project. These belong to the researcher.

Everything you do is recorded with your name and, where you have one, your ORCID iD, and is
credited with a CRediT role: *Data curation* for edits, runs and notes, and *Validation* for
clearing a step, a review or a co-approval. This credit travels with the deposit package's
provenance.

## Pausing a project

A pause stops every step in the project that is not advice, and the deposit, until a steward lifts
it. Use it when something must not go further until it is checked: possible personal data, a
consent question, or an embargo.

- **Pause project** asks for a reason, which the researcher sees.
- The researcher can still read, talk to the advisers and write to you.
- A run already in progress finishes and is recorded.
- A pause never lifts itself. You, or anyone in your team, lift it with **Lift pause**.
- If the researcher withdraws the escalation, the pause stays, and your team keeps access until
  the pause is lifted.
