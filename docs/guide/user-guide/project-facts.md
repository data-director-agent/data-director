# Deciding project facts

While agents check your project they find things that later steps need to know. Examples are a
duplicate file, a file of coordinates that may need withholding, the funder, or a repository
your funder requires. Data Director keeps these as **proposals**. An agent drafting your README or
metadata record is given only what a person has decided, never a proposal. So you decide each one.

## Deciding a proposal

1. Open the project's page and choose the **Project facts** tab. From a conversation, the
   quickest way is a link: when an agent proposes facts, its card in the conversation lists them
   with **Review them in Project facts**, and the project pane beside the conversation has a
   **Review** button for each kind of fact waiting. Either takes you to those facts, marked, with
   the first one in view.
2. Under **Proposed by agents**, each proposal says what it would decide, why the agent proposed
   it, and which agent did.
3. Choose one of:
   - **Confirm it as proposed**, to record it as it is.
   - **Change it, then record my version**, to set the values yourself, for example to publish a
     location only at the level of a region.
   - **Reject it**, if it is wrong.
4. Add a reason if a colleague should know why. It is kept in the project's record, and no
   agent is given it.

## Talking a proposal through

If you are not sure about a proposal, choose **Discuss this with Data Director** on its card. A
new conversation opens with a question about the proposal in the message box: what it would
decide, which agent proposed it and why. Nothing is sent until you send it, so you can change
the question or remove the agent's reason first. Data Director can explain and advise, but it
cannot decide the fact: come back to **Project facts** to confirm, change or reject it.

## Describing your data

When you tell Data Director what data your project collects or produces, how, in which formats
or in what volume, it proposes a **description of the project's data** in your own words. Check
it under **Proposed by agents** and confirm or correct it. Once it is decided, every agent in the
project is given it, in this conversation and in any you start later. For example, the
Documentation Editor writes it into your Data Management Plan's **Data description and
collection** section, so you do not have to say it again. You can also add a description
yourself with **Add a fact**.

## Changing what was decided

Under **Decided**, you can change or remove a fact that stands. **Add a fact**
records one of your own, such as a funder no agent found.

## Funders and their identifiers

When the Policy Adviser checks a funder's policy, it looks the funder up in ROR, the Research
Organization Registry. If the name means exactly one organisation there, it proposes the funder
as a fact with its ROR identifier and its Crossref Funder ID, both from ROR's record, so you do
not need to type them. ROR now holds the Crossref Funder Registry's identifiers. If a name could
mean more than one organisation, such as "NERC", the adviser asks which you mean instead of
proposing one. If you added a funder by name only, its proposal fills in the identifiers for that
same fact when you confirm it.

## Who decides

Anyone working on the project may decide which files go in, the funders and the repositories
required. Whether sensitive data may be published, and the licence, have legal consequences, so
only an owner of the project may decide them.

## Where it goes

Every agent that drafts the project's documents is given the facts that stand. The last
decision on each counts. An agent that sends data to an AI model hosted outside your institution
is given them unless your institution's deployment says otherwise.
