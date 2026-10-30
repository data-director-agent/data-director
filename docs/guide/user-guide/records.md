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

## Where you can see it

- **After a run**, the page shows the stages it went through, the outcome, the result and the
  evidence.
- **In a conversation**, each step handed to an agent appears as a card. Opening the card shows
  that run in full.
- **On an agent's History tab**, every stored run for that agent is listed, newest first. Each
  reopens in the same view as when it ran.
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
for your iD and your name only. Where nobody signs in, the banner says so, and every run is
recorded as acting for the person who set up the deployment.

In this version anyone who can open the app, or who is signed in to it, can see every run and
conversation in it (TODO(#153)). Do not enter anything you would not want others with access to
the app to read.

If you report a problem from the app, the report includes what you type and, only if you agree,
the identifiers of the run and conversation. It never includes your inputs or results.

## How long records are kept

Records are kept until whoever runs the deployment removes them. The app does not yet let you
delete a run or a conversation, and there is no automatic expiry (TODO(#41, #156)). Ask the
person who runs your deployment if you need a record removed.
