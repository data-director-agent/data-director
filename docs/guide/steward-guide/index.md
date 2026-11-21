# Data Steward's Guide

For data stewards, research data librarians and others in a research data management team who
support researchers using Data Director. The Blueprint calls you *data support professionals*
(§2). Researchers have the [user guide](../user-guide/index.md). The people who install and run
an instance have the [operations guide](../operations/index.md), and some of them may also be
you.

Data Director helps researchers prepare their data for deposit. It does not replace you
(Blueprint §3.3). When an agent cannot or must not go on, or the researcher wants a person, the
matter comes to you. You also own the rules every run is held to.

## What a steward does in Data Director

- **Owns the policy.** You decide which agents run, what each may do, which actions need a
  person's approval and what may reach a hosted AI model. These are set in the institutional
  profile. See [The policy and the profile](policy-and-profile.md).
- **Answers escalations.** A researcher asks for help, or confirms an agent's offer to ask you.
  You take the escalation, reply, and resolve it or hand it back. See [Escalations](escalations.md).
- **Steps into a project.** While an escalation is open, you can open the researcher's project, see
  what they see, write to them, propose edits, run agents, clear a step that policy stopped, and
  pause the project. See [Working in a project](working-in-a-project.md).
- **Helps get a project ready to deposit.** See [Deposit readiness](deposit-readiness.md).
- **Keeps an eye on the whole picture** without reading anyone's work. See [Overviews](overviews.md).

Throughout, the researcher stays in charge of their work. You propose, and they decide. They
approve their documents and their deposit (R2), and they can see every time you look at their
project and everything you do in it. [Good practice](good-practice.md) explains why.

## What works today

Data Director is alpha software, and most of this guide describes features specified in
[Data stewards](../../specs/stewardship.md) and not yet built. Each page says plainly what works
now; anything not built carries a note linking to its issue.

| Capability | Status | Issue |
|---|---|---|
| Reading and reviewing the policy on the Policy page | Works | — |
| Steps referred to a data steward stop, with the reason shown | Works | — |
| Being named as a steward in the profile | Not built yet | [#154](https://github.com/data-director-agent/data-director/issues/154) |
| Escalations and the queue | Not built yet | [#373](https://github.com/data-director-agent/data-director/issues/373), [#376](https://github.com/data-director-agent/data-director/issues/376) |
| Opening a project as a steward, and acting in it | Not built yet | [#374](https://github.com/data-director-agent/data-director/issues/374), [#376](https://github.com/data-director-agent/data-director/issues/376) |
| Clearing a referred step | Not built yet | [#16](https://github.com/data-director-agent/data-director/issues/16), [#374](https://github.com/data-director-agent/data-director/issues/374) |
| Pausing a project | Not built yet | [#374](https://github.com/data-director-agent/data-director/issues/374) |
| Notes and co-approval before deposit | Not built yet | [#1306](https://github.com/data-director-agent/data-director/issues/1306) |
| Overviews | Not built yet | [#232](https://github.com/data-director-agent/data-director/issues/232), [#1307](https://github.com/data-director-agent/data-director/issues/1307) |
| Notifications | Not built yet | [#378](https://github.com/data-director-agent/data-director/issues/378) |

## In this guide

| Page | Read it to |
|---|---|
| [Becoming a steward](becoming-a-steward.md) | See how the profile names stewards and teams, and what researchers are told. |
| [The policy and the profile](policy-and-profile.md) | Read and review the rules every run is held to. |
| [Referrals and reviews](referrals-and-reviews.md) | Understand which outcomes and reviews come to you, and who approves what. |
| [Escalations](escalations.md) | Take, answer, resolve and hand back the matters researchers send you. |
| [Working in a project](working-in-a-project.md) | Open a researcher's project and help in it. |
| [Deposit readiness](deposit-readiness.md) | Help a researcher through the checks before deposit. |
| [Overviews](overviews.md) | See your team's projects and the wider picture. |
| [Notifications](notifications.md) | Choose what you are told about. |
| [Good practice](good-practice.md) | Act in a way researchers can trust. |

The design behind these pages is in [Data stewards](../../specs/stewardship.md) and
[Steward escalation flows](../../ui/steward-escalation-flows.md). If something here does not
match how your team works, [tell us](../user-guide/feedback.md).
