# What the Data Director records

The Data Director keeps a record of everything its agents do for you. Whenever an agent works on
your data or metadata, the app stores what it was asked, what it answered and what it relied on.
You, and anyone reviewing your work later, can then check how a recommendation was reached rather
than take it on trust.

This page explains what is recorded, where you can see it, and who else can.

## When a record is made

A record is made for every run: each time an agent is asked to do something, whether you start it
from an agent's **Run** tab or the Data Director hands a step to an agent during a conversation.
This applies in every phase of the [workflow](workflow.md).

A run is recorded even when it does not produce a result. If the agent declines to answer, refers
the matter to a person, or a check stops its result reaching you, the record says so and why. See
[Understanding outcomes](outcomes.md).

## What a record contains

| Part | What it tells you |
|------|-------------------|
| **Your request** | What the agent was given: the input from the form, or your message in the conversation. |
| **The result** | The [outcome](outcomes.md), the agent's statement, and anything it produced, such as a list of recommended standards. |
| **The evidence** | The sources the result rests on, such as entries in a registry of standards or repositories. |
| **The checks** | Whether the result cites only what the agent actually consulted, and whether each cited source matches a trusted copy of it. |
| **The steps taken** | A timeline of what happened during the run, from the request arriving to the result being returned. |
| **Who and when** | Which agent ran, which version of it, the person it acted for, and the date and time. |

Each run also gets a provenance record in a standard format
([Process Run Crate](https://www.researchobject.org/workflow-run-crate/profiles/process_run_crate/)).
It describes the run in a form that other research tools understand, so it can travel with your
data if it needs to.

The agents do not write these records themselves. The part of the Data Director that runs every
agent, the harness, writes them, so an agent cannot leave out or alter what it did.

## Conversations

Your conversations with the Data Director are recorded in the same way. Each message you send is a
run, and each step it hands to another agent is a run of its own, linked to the message that led
to it. That is how a past conversation reopens with every result in place, and how the Data
Director remembers what was said earlier in it.

## Projects

Each conversation is started in a project of its own. The project keeps the inventory of your
files that you attach ([Making an inventory](making-an-inventory.md)) and the documents agents
draft for you, with every decision you make on them. Nothing is removed from a project's record:
a newer inventory is added beside the earlier one, and the latest counts. An inventory holds facts
about your files and never their content. When an agent uses an AI model, the facts it is given
from the inventory can be sent to that model's provider (see AI models, below).

**Projects**, the first item in the menu at the top, lists your projects, the one you worked in
most recently first. Each is named after its first conversation, and says how many files its
inventory describes and how many of its documents are waiting for you to review. Select one to
read its documents and decide on them.

A project's page lists its documents on the left, those waiting for you first, and opens the one
you choose beside them. **Preview** shows the document laid out, with a data dictionary as a
table. **Source** shows the exact text your decision is on, which is what goes into the deposit
package. **Versions** lists each earlier version, what was decided on it and why, and what each
version changed. Your decision form is under the document. If you edit the text, the preview
shows your version before you approve it.

## Where you can see it

- **After a run**, the page shows the stages it went through, the outcome, the result and the
  evidence.
- **In a conversation**, each step handed to an agent appears as a card. Opening the card shows
  that run in full.
- **Past conversations** reopen with their results in place.

## AI models

Some agents use an AI model from an external provider. What you type into the conversation, and
what an agent returns about your data, can then be sent to that provider, whose own terms decide
how long it is kept. An agent's **About** tab lists the models it sends data to, or says that it
calls none. Your institution decides which models are used: see
[AI models](../operations/ai-models.md).

## Who can see the records

The records are kept by the deployment of the Data Director you are using, on your institution's
server or on your own machine. They are not sent to the Data Director project.

Where the deployment signs people in, you sign in with your ORCID iD, and each run is recorded as
done for you, with ORCID named as the one that vouched for who you are. Data Director asks ORCID
for your iD and your name only; select your name in the banner to see them on your profile page. Where nobody signs in, the banner says so, and every run is
recorded as acting for the person who set up the deployment.

Where people sign in, each person sees only their own runs, conversations and projects. A
project's documents, inventory and progress can be read only by the person who created it, even by
someone else who has its address; sharing a project with colleagues is TODO(#389).

If you report a problem from the app, the report includes what you type and, only if you agree,
the identifiers of the run and conversation. It never includes your inputs or results.

## The rules each run is held to

Every run is checked against the deployment's policy before it starts, and its record names that
policy, for example `profile:data-director-app@v7`. Select **Policy** in the banner to see it: which
agents may run, what each is allowed to do, and which actions need a data steward's approval.
A data steward sets the policy; it cannot be changed from the app.

## How long records are kept

Records are kept until whoever runs the deployment removes them. The app does not yet let you
delete a run or a conversation, and there is no automatic expiry (TODO(#41, #156)). Ask the
person who runs your deployment if you need a record removed.
