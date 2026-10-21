# ADR-0028: The app's entry point is the orchestrator conversation

**Status:** Proposed
**Date:** 2026-10-21

Amends [ADR-0024](0024-app-shell.md) (the app's home page) and
[ADR-0017](0017-policy-is-the-deployments.md) (a new profile key, `orchestrator`).

## Context

The app's home page is a directory of agents, each with Run, About and History pages. That is
close to the workbench's Inspect page, a test bed for the engineers who write agents. The
Blueprint describes something else. Its presentation layer is a "web app providing a chat
interface and feedback mechanism" (§9.2, Table 5), over an application layer that orchestrates
user requests and coordinates the agents (§9.3, Table 6, "AI Model Orchestration"). A person
talks to one Data Director; the specialist agents support it.

ADR-0024 removed the Gradio chat and said it would return as an orchestrator under `delegation`
grounding (ADR-0012, #21). This decision says where that orchestrator sits in the app. Earlier
decisions constrain the answer:

- The shell names no agent and holds no policy (ADR-0024 §1, §4).
- An orchestrator delegates only through the conductor, under a grant; it is found by grounding
  mode, never by name; and every delegated child is labelled `agent_id@agent_version`
  (ADR-0012 §5, §12).
- The deployment's profile, not the agent or the shell, decides what may run (ADR-0017).
- The UI notes ask for chat for intent and a structured surface for the work
  (`docs/ui/best-practices.md` §1, §9). Their evidence is weak, so this is a design hypothesis to
  test.

## Decision

1. **The app opens on a conversation with the orchestrator.** The orchestrator is an agent
   whose grounding mode is `delegation`. The shell is told which agent it is by the harness and
   never names it.
2. **The profile names the orchestrator.** A new optional profile key, `orchestrator`, holds one
   `agent_id`. The agent must also be listed under `agents`, and its grounding mode must be
   `delegation`; otherwise the profile is refused when the app starts, with one line, like any
   other malformed profile. A change to it raises the profile's `version`, so stored runs say
   which orchestrator the rules named.
3. **The default is written in the reference profile, not in code.** The app's reference profile
   (`app/config/profile.yaml`) names the orchestrator released in this repository, at present
   `director.stub`. A deployment that wants another names it in its own profile. Neither the
   harness nor the shell holds a fallback agent identifier.
4. **Without the key, the choice is made only when there is nothing to choose.** When a profile
   has no `orchestrator` key and exactly one permitted, registered agent has `delegation`
   grounding, that agent is the orchestrator. When there is none, or more than one, the home page
   says so and links to the agent directory. When the named orchestrator is not available (its
   service is not running), the home page says that and links to the directory. The app does not
   fall back to another agent in any of these cases.
5. **The per-agent pages remain.** Run, About and History stay, one step away from the
   conversation, so a person can see what each agent does and inspect its runs.
6. **Every delegated child is named and linked.** The conversation shows each child as
   `agent_id@agent_version` and links it to its own run.
7. **A turn is a governed invocation.** Each message is one invocation of the orchestrator
   through the conductor (ADR-0012 §1), and each hand-off is a child invocation under the grant
   the conductor issues (ADR-0012 §5). The app must issue that grant (#129).
8. **What the conversation is not.** It does not bypass the conductor, and the shell does not
   route, classify or forward a person's message to a sub-agent itself. Routing is the
   orchestrator's, and every hand-off is stored.

TODO, not decided here: whether a person may still run a sub-agent directly from the app or only
through the orchestrator, and whether the profile decides that.

Rejected:

- **Keeping the directory as the home page, with the conversation as one more page.** The
  Blueprint puts the chat interface first, and a person should not have to choose an agent before
  saying what they need.
- **The shell routing messages to sub-agents.** That would put routing, a policy decision, in the
  shell, and its hand-offs would not be recorded as delegations on any envelope.
- **Falling back to a named or first-listed agent in code.** A person would be talking to an
  agent they did not know had been chosen for them, and a steward reading the profile could not
  see the choice.
- **Choosing the orchestrator in the app's own configuration (`agents.yaml`, an environment
  variable).** Which agent a person talks to first is a policy choice, and ADR-0017 puts policy
  in the profile, which a steward reviews and every run cites.

## Dependencies introduced

None.

## Consequences

- The home page and navigation change (#131, #132). The directory becomes its own page.
- The home page needs the app to issue delegation grants (#129) and a conversation API over the
  conductor (#130) before it works. Until then `director.stub` abstains in the app.
- The profile loader refuses keys nothing enforces, so `orchestrator` is added to the loader,
  the profile vocabulary (`workbench/profiles/README.md`) and the reference profile with the home
  page that reads it (#131), not before. The workbench's profiles may leave it out.
- When a model-backed orchestrator is released, the reference profile is changed to name it, in
  an ordinary profile change with a new `version`.
- Until a model-backed orchestrator exists (#21), the conversation is with the rule-based
  `director.stub`: replies are templates, and routing follows its `routing.yaml`.
- A future contributor must not name the orchestrator in `app/web/src`, route messages in the
  shell, or call a sub-agent from the conversation outside the conductor without revisiting this
  decision.
