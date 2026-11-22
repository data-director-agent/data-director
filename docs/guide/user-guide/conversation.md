# Using the conversation

The conversation is the home page of the app. You write to the Data Director in plain language,
and it replies, asks you questions, drafts documents and hands steps to agents that can help. This
page describes what is on the screen, how to write a message and attach a file, and what the five
stages shown beneath a message mean while it is being answered.

You do not need the conversation to use the app: you can also open an agent directly and use its
**Run** tab ([Running an agent](running-an-agent.md)). The conversation is the usual way in
because it follows the [workflow](workflow.md) with you.

## What is on the screen

The conversation belongs to a [project](records.md#projects), and the page is laid out around it.

| Part | What it is for |
|------|----------------|
| **Data management phases** (strip above) | The six phases of the [workflow](workflow.md). Open it to see, for each step, the agents that serve it. |
| **Conversations** (left) | The project's other conversations. Select one to reopen it with every result in place, or start a new one. |
| **The conversation** (centre) | Your messages and the replies, with the message box beneath. |
| **Project** (right) | An overview of the project: its current state, such as the repository chosen, the files attached to it and its documents. |

A conversation is kept in the address of the page, so reloading the page or following a link to it
reopens the same conversation.

### Starting a conversation

With no project open, your first message starts a project. **New conversation** starts another
thread in the project you are working in. An empty conversation offers **Suggested ways to start**,
chosen from where your project has reached: each one puts a message in the message box for you to
edit and send. Nothing is sent until you send it.

The same applies to a step in the phases strip: choosing it starts a new conversation with that
step's message in the box. If you were already writing something, the app asks before it replaces
your text.

### Writing a message

Type in the message box and select **Send**, or press Ctrl+Enter. While a reply is awaited, your
message stays in the conversation, a line says the Data Director is working on a reply, and the
box waits. You can leave the page and come back: the conversation is stored.

Answer in your own words. Where the Data Director asks a question with a few known answers, such as
which [entry point](workflow.md#choose-an-entry-point) you mean, the choices take the message box's
place, as buttons, or as tick boxes where more than one may apply. You never have to use them:
select **Reply in my own words instead** to type a message, which is sent as your reply, and
**Answer the questions instead** to go back to the choices, as you left them. **Attach a file**
sits beside the choices too, so a file you attach goes with your answers. A series of questions
lists your answers for you to check after the last one. A new project's
[setup questions](workflow.md#choose-an-entry-point) take the message box's place in the same
way, after any questions the latest reply asks. In a text box for a longer answer, Enter
starts a new line; press Ctrl+Enter (Cmd+Enter on a Mac) to submit the answer, as in the message
box.

### Attaching a file

**Attach a file**, dragging a file onto the message box or the questions, or pasting one, adds it
to your message or your answers.
Two kinds are accepted:

- **An inventory** of your files, which describes them without holding their content
  ([Making an inventory](making-an-inventory.md)).
- **A supporting document**, as plain text or Markdown
  ([Attaching a document](attaching-a-document.md)).

A message can carry one of each. Neither goes into the text of your message: it is stored in the
project. Before anything is attached, a dialog shows you what will be kept, and the file is attached
only when you confirm. Discarding it stores nothing.

### Documents the Data Director drafts

When a reply includes a draft, such as a README or a data dictionary, it appears in the
conversation as a document card. You decide on it from there or from the project's documents page.
Every decision is recorded ([What the Data Director records](records.md)).

### If a reply fails

A reply that fails says so in plain words: that the Data Director could not answer, that nothing
was changed, and that anything your message attached is kept in the project. The latest message
then offers **Try again**, which sends it again as a new message. A detail for the people who run
the Data Director is kept behind a closed disclosure, **Details for whoever runs Data Director**.

## The five stages of a reply

While your message is being answered, a **Progress** list appears beneath it. It is the same five
stages, in the same order, for every message and every agent. They are fixed by the harness, the
part of the Data Director that runs every agent and writes the record of it
([What is recorded](records.md)). The agent cannot add, remove or reorder them.

| # | Stage | What it answers |
|---|-------|-----------------|
| 1 | **Policy gate** | May this agent run at all? |
| 2 | **Input check** | Is what the agent was given fit for it, and may it go where it is going? |
| 3 | **Agent** | The work itself. |
| 4 | **Grounding check** | Does the result cite only what the agent actually did? |
| 5 | **Source check** | Does each cited source match a trusted copy of it? |

Four of the five are checks. The third, **Agent**, is the agent doing its work: it is in the list
because the checks either side of it are defined by it. The first two checks happen before the
agent runs, and the last two after it, before you see anything.

### 1. Policy gate

Your institution decides which agents may run, with which settings, and which kinds of action need
a data steward's approval. These choices are in the deployment's policy profile
([The policy and the profile](../steward-guide/policy-and-profile.md)), and the gate applies them
to this agent before anything else happens.

- If the agent is not permitted, the run fails and the agent is **not run**.
- If the agent's kind of action needs approval, the run ends as *referred*, with the reason that
  the policy requires approval, and the agent is **not run**. Asking a steward to approve a run
  from the app is not built yet (TODO(#16)).

### 2. Input check

Before the agent is given your request, the Data Director checks it in two ways:

- **It fits the agent.** What the agent is asked must match what its card says it takes. A request
  the agent does not accept, or that fails its rules, is refused here, and the agent is not run.
- **It may go where it is going.** Some agents use an AI model hosted outside your institution, or
  an external tool. Your institution's profile says which kinds of project content may be sent to
  one. Content that may not be sent is held back from the agent rather than sent anyway.

See [AI models](../operations/ai-models.md) and the [Privacy notice](../privacy.md) for what can
leave your institution.

### 3. Agent

This is the stage where the agent works. While it runs, the stage counts the time and lists what
the agent is doing as it happens: the agents it **Asked** or is **Asking**, and the tools it
**Used** or is **Using**. The latest five are shown and earlier ones are counted. If nothing new
has happened for 20 seconds, the list says that the agent is still working, because some questions
take a minute or two.

The agent's own account of what it did is not trusted for the next two stages. They compare it
against what the harness recorded.

### 4. Grounding check

Nothing an agent presents as a result should rest on something it cannot account for. The agent
lists what its result relies on, and the grounding check compares that list against the record of
what the agent actually did during the run, such as a registry record it fetched, the input it was
given or the runs it delegated.

This is a **consistency check**. It shows that the agent's account of its run agrees with itself
and with what the harness recorded. It does not show that an agent's reasoning was sound, or that a
model read a record rightly: that is a question for evaluation, not for this check
([Evidence and grounding](../../specs/grounding.md)).

The stage ends as **Passed** or **Failed**.

### 5. Source check

Each source a result cites is identified by a content hash. The source check looks the source up in
a copy the harness holds, independently of the agent, and tests that it holds the record named and
that the record hashes to the same value. An agent cannot cite a record that is not in the copy, or
alter one and still pass.

Where the harness holds no copy of a source, the source is reported as *unresolved*. That is not a
failure, and it is never counted as verified.

The stage ends as **Passed** or **Failed**.

### What each state means

| State | Meaning |
|-------|---------|
| **Waiting** | Not started yet. |
| **Running** | In progress, with the time it has taken. |
| **Done** | The stage finished. Used for the policy gate, the input check and the agent. |
| **Passed** | The check ran and found nothing wrong. Used for the grounding and source checks. |
| **Failed** | The check found a problem. |
| **Stopped** | The stage was cut short, for example by cancelling the run. |
| **Not reached** | An earlier stage ended the run, so this one never started. |

A stage that stops a run is not shown as an error of yours or of the app: it is the system working
as designed. The reply below the list says what happened and what to do next
([Understanding outcomes](outcomes.md)).

### When a check fails

If the grounding check or the source check fails, a result that would have *succeeded* becomes a
*failed* outcome, and the result and its evidence are **withheld**, not shown with a warning. The
two verdicts are kept separately in the run's record. Try the message again; if it keeps failing, give the
run to whoever runs the Data Director.

If the policy gate or the input check ends the run, the agent never ran, so there is no result to
withhold. The reply gives the reason.

### Cancelling a run

**Cancel the run** appears beside the progress list while the run is under way. The run is stopped
and recorded as cancelled. An agent already working may carry on until it returns; its answer is
discarded, and the record still shows what it did. A cancelled run keeps its place in the
conversation until your next message.

## Following a run in more detail

- The **activity log**, a page of its own in the main navigation, lists every run Data Director
  has recorded for you, newest first, with its outcome and a link to its record. For the runs you
  sent from this tab since you opened it, it also shows each step: the stages, each check's
  report, tool calls and the agents delegated to, each linked to its record. The server keeps a
  run's record, not its steps, so after a reload or in another tab you see the runs and their
  outcomes, not their steps.
- A delegated agent's card in the conversation opens its own record, with its outcome, its result
  and the evidence it rests on.
- Every run, including cancelled and failed ones, is recorded
  ([What the Data Director records](records.md)).

## Related pages

- [The workflow](workflow.md): the phases and entry points a conversation follows.
- [Understanding outcomes](outcomes.md): succeeded, abstained, referred and failed.
- [Running an agent](running-an-agent.md): the same stages, from an agent's **Run** tab.
- [What the Data Director records](records.md): what is kept about each run.
