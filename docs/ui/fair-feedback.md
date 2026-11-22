# FAIR feedback in the app

*The design for #433, part of #430. The [App](../specs/app.md) spec says what is built. What is
not built yet is marked as a to-do naming the issue that will build it.*

## Purpose

Researchers should see how FAIR their project's metadata record is while they work on it, and
each improvement should show, so that improving it pays off as they go (#430). ORA's FAIR score
(<https://ora.ox.ac.uk/FAIR>) was the example. This note covers three things:

1. how a researcher **asks** for FAIR feedback;
2. how they see **where the record stands**;
3. what **draws them to improve it**, without turning the work into a game.

## What it is built on

The FAIR Assessor (`advisor.fairness`) gives feedback on the project's draft metadata record at
any point in the work ([Agents](../specs/agents.md), #432). Its `FairnessReport` holds:

- twelve rule checks, each tied to a FAIR sub-principle (`F2`, `R1.1`, …);
- for each of F, A, I and R, how many checks were met out of how many were assessed;
- which checks are newly met since the version a person approved last;
- the checks to act on first;
- the checks left until deposit, which are not counted against a draft;
- what the checks are not.

The app shows that report and adds nothing to it but a comparison between reports. It
recognises a report by its payload class, `FairnessReport`, never by the agent that returned it,
as it recognises a repository shortlist (App spec, invariant 1). It reads every report stored in
the project from `GET /api/projects/{id}/runs?payload=FairnessReport`. That endpoint names no
class of its own: the shell passes the class.

## Decisions

### No score

The app shows counts, such as "Findable: 2 of 3 checks met", and never a percentage or a single
FAIR score. The reasons:

- R4 says the Data Director does not replicate a full FAIRness evaluation. A score would read as
  one, and as more precise than twelve presence checks are.
- Community tools score differently and disagree (Blueprint §10). Which frameworks to use is still
  open (#431). A score now would have to be unlearned later.
- A score would change `FairnessReport`, a fixed format, and its spec.

Each count names what it counts. Every view says "Not a FAIRness evaluation" and names the run
that gave the report, as `agent_id@version`, with its date and the version of the record it
checked.

### Asking for feedback

Feedback is asked for in the conversation, as everything else is. The orchestrator delegates it,
and the shell does not route (App spec, invariant 3).

- In the project pane beside the conversation, **How FAIR is it?** (or **Check again**, or
  **Check the new version**) puts a prepared question in the message box, unsent. This is the
  same pattern as "Ask about the next step".
- Each next step has **Ask how**, which puts a question about meeting that one check in the
  message box.
- The pane shows the section only where an agent in the deployment returns a `FairnessReport`,
  which the shell reads from the agents' payload classes.
- With no metadata record yet, the section says feedback comes once there is a draft, and offers
  no question.
- The project's **FAIR feedback** tab has no message box, so it quotes the question to ask. One
  step from the tab is TODO(#1418).
- Reassessing on its own when the record changes is TODO(#1416).

### Where the record stands

- **Four meters.** One row for each of F, A, I and R: a meter, its count in words, and an icon
  with a word ("All met", "1 to do", "Checked at deposit"). Neither the bar nor its colour carries
  the meaning alone, and each meter's accessible name says the count.
- **A principle a draft cannot meet.** At present every Accessible check needs the repository.
  That row says "Checked at deposit" and draws no empty bar, so that a draft is not shown as
  failing what only deposit can supply.
- **Every check.** On the tab, every check sits under its principle: met, to do with its
  recommendation, or checked at deposit.
- **What these checks are not.** The report's limitations, closed until opened.

### Drawing researchers to improve it

The design uses progress, not prizes: no points, badges, streaks or leaderboards.

- **Next.** The report's two next steps come first, each a small thing to do, with *Ask how*.
- **New since the last check.** The checks met since the report before, marked off as each
  improvement shows, and "up from n" on a principle whose count rose. With only one report,
  the section shows what the report says is new since the version approved. The agent comparing
  with its previous assessment itself is TODO(#1417).
- **Out of date.** When the record has a newer version than the one assessed, the pane says so
  and the button becomes **Check the new version**. This prompt closes the loop.
- **Over the project.** The tab lists each report stored in the project as a table row: date,
  record version, and the four counts. Improvement over the whole project can be read row by row
  and read aloud.
- **Ready for deposit checks.** When every check a draft can meet is met, the report says so and
  the tab points on to the deposit checks. The end of the loop leads to the next step of the
  work rather than to a trophy.

## Accessibility

- Every state has a word and an icon as well as a colour. Colours come from tokens: ok for met,
  warn for out of date.
- Meters have accessible names. The history is a table with row and column headers, which
  scrolls at narrow widths rather than breaking words.
- Headings follow on from the section they sit in. Axe checks the pane, the tab and the browser
  test at 1280 and 320 pixels (`app/web/e2e/fair.spec.ts`).

## Not decided here

- Which FAIR frameworks and community tools the app shows, and whether each institution chooses
  them in its profile: #431.
- Results from a community tool such as F-UJI beside the rule checks, once the dataset is
  published: TODO(#704).
