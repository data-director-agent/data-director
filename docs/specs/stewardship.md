# Data stewards

## Intent and scope

The Data Director supports data stewards; it does not replace them (Blueprint §3.3). The Blueprint
calls them *data support professionals*: "a secondary but important user group, both as direct
users of the tool and as those who may configure, deploy, or provide support for it on behalf of
their institution" (§2). This spec says who a data steward is in a deployment, how a matter reaches
one, what a steward may see and do in a researcher's project, and how every step of that is
recorded and shown to the researcher. It settles the questions of #372 and the role part of #154.

The specs use "steward" in two senses, and this spec covers both as one role:

- the person who owns the deployment's **policy**: the institutional profile, its action classes
  and what needs approval ([Policy and identity](policy-and-identity.md)). How a steward edits the
  profile from the app is TODO(#225); today a steward reads the profile on the Policy page and
  changes it through the operator ([the steward's guide](../guide/steward-guide/policy-and-profile.md));
- the person who **helps researchers**: who receives an escalation, opens the researcher's project
  and acts in it.

In scope: deployment roles (researcher, steward, administrator) and where they come from;
escalation; a steward's access to a project and the closed list of what a steward may do there;
pause; the mandatory reviews and who makes each; a steward's overviews; and how all of this
behaves in a deployment with no stewards (C17).

Out of scope: who may edit the profile from the app (#225); the security of sign-in itself
([Policy and identity](policy-and-identity.md)); notification transport beyond what a message may
hold (#378); and the Blueprint's other data-support-professional uses in §4.1 that act on systems
outside a project, such as managing access in a repository, which no agent performs.

The experience is designed in [Steward escalation flows](../ui/steward-escalation-flows.md), and
the people who do this work have a [Data Steward's Guide](../guide/steward-guide/index.md).

**What is built.** The referral: the policy gate's `referred(policy_requires_approval)` names
`referred_to: data_steward` and does not run the agent ([Policy and identity](policy-and-identity.md),
`dd_harness.refusals`), and the Policy page shows each step a steward must approve
([The app](app.md)). Deployment roles (invariant 1). Everything else in this spec is the intended
design; each invariant names the issue that builds it.

## Invariants

1. **A person's deployment role comes from the profile.** The profile's `stewardship` key names
   the deployment's steward teams, and its `administrators` key the administrators. Each team has
   an identifier, a name shown to researchers, its members as principal identifiers (an ORCID iD
   for ORCID sign-in), the labels of the projects it supports, an optional contact for when no
   steward can help (an address or a page, shown as given), and an expected response time. A
   principal identifier is written as recorded: for ORCID sign-in, the iD as a URL, and a bare iD
   is refused at load because it would name nobody. Everyone who signs in is a researcher, who may
   hold projects of their own; a person a team lists is also a steward, and a person
   `administrators` lists is also an administrator, who administers the workbench and has no
   access to anyone's project by it. The session response names each person's roles and teams. A
   role never comes from an environment variable: `administrators` replaced the workbench's
   former `DD_WORKBENCH_ADMINS` list, and a deployed workbench runs under the instance's profile.
   Group or entitlement claims from an institutional identity provider may later map to a team,
   in the same key, TODO(#936). Like every profile key, `stewardship` is refused at load unless
   something enforces it, and is recorded with every run through `policy_bundle_ref`; until
   steward access to a project is built, a profile that sets `visibility: scope` or
   `deposit_co_approval: true` is refused, TODO(#374, #1306). Built:
   `dd_harness.stewardship`.

2. **A deployment role never makes anyone a member of a project** ([Projects](projects.md),
   invariant 16). A steward reaches a project by a separate path beside
   `dd_harness.project_access.role_of`, which answers "steward of this project" or nothing. Every
   check that `role_of` answers today also asks the steward path: the app's `in_project`,
   `Governance.role` and the conductor's check before a run. A person who is both a member of a
   project and a steward acts as a member there, and may not act as its steward (invariant 7).
   Not built yet, TODO(#374).

3. **A steward sees a project only while the profile's visibility allows it, and every look is
   recorded.** `stewardship.visibility` is one of:

   | Value | A steward may open a project |
   |---|---|
   | `escalated` (the default) | while it has an escalation routed to the steward's team that is `open`, `taken` or `waiting for researcher`, or a pause the team holds (invariant 8) |
   | `scope` | as `escalated`, and also any project whose owners have chosen the steward's team as its support team, from the labels that team supports |

   No value lets a steward see every project in the deployment. A project outside a steward's
   visibility is refused with status 404, as for any non-member, so that the refusal does not
   reveal that it exists. Each time a steward opens a project, or reads any of its content, the
   harness appends a `steward_viewed` event naming the steward; repeated reads by the same steward
   on the same day append one. The researcher sees each one in the project's log (invariant 10).
   Not built yet, TODO(#374).

4. **An escalation is a record in the project's log, not a store of its own.** Its events are
   `escalation_opened`, `escalation_taken`, `escalation_released`, `escalation_waiting`,
   `escalation_replied`, `escalation_resolved`, `escalation_handed_back`, `escalation_withdrawn`
   and `escalation_reopened`, each naming whom it acted for and its cause like every project event.
   Its states and the moves between them are the table in
   [Steward escalation flows](../ui/steward-escalation-flows.md#escalation-states); the harness
   refuses any other move. `escalation_opened` records its **origin** (the researcher; the policy
   gate's referral, with the invocation; an agent's `abstained` or `referred` outcome, with the
   invocation; or the orchestrator's offer), the **team** it is routed to, the researcher's note,
   and the **scope shared** as the researcher saw it when they confirmed it. A re-opened escalation
   keeps its history. The listing index that finds a person's projects in one query
   ([Storage](storage.md)) gains a team index, so that a team's queue is one query too. Not built
   yet, TODO(#373).

5. **The agent offers; a person confirms.** No escalation exists until a person confirms it, having
   seen what will be shared. An agent's `abstained` outcome offers an escalation and never raises
   one. The exception is a mandatory review (invariant 9): the step is stopped whatever the
   researcher chooses, and the offer is how its reviewer is reached. Not built yet, TODO(#375).

6. **What a steward may do in a project is a closed list.** Each action is checked by the harness
   against the steward's access (invariant 3) and recorded as an event naming the steward as whom
   it acted for, with `acting_as: steward`:

   | Action | Recorded as | Who decides the outcome |
   |---|---|---|
   | Read the project | `steward_viewed` | — |
   | Write to the researcher | `steward_message`, shown as from a named person, never as an agent | — |
   | Propose an edit to a document | a new `proposed` version by `ProjectStore.edit`, marked as the steward's | the project's owners approve or reject it ([Projects](projects.md), invariants 11 to 14) |
   | Run an agent in the project | a run acting for the steward, with the project as context; its drafts land as `proposed` versions | the project's owners |
   | Clear or refuse a gated action | `gate_cleared` or `gate_refused`, naming the referred invocation and a reason | the steward (a §5.1 policy exception) |
   | Pause the project, or lift a pause | `project_paused`, `project_resumed`, each with a reason | the steward's team (invariant 8) |
   | Note on a deposit review item; co-approve a deposit | `steward_note`; `deposit_co_approved` | the researcher approves the deposit (invariant 7) |
   | Take, release, ask, resolve or hand back an escalation | the escalation events (invariant 4), resolving and handing back with a note | — |

   A steward cannot decide a project fact, approve or reject a version, approve a deposit, change
   membership, or delete or restore a project. A researcher cannot do any of the steward's
   actions, by any route. Not built yet, TODO(#374).

7. **Clearing a gate is not approving the content** (§5.1 against R2 and §8). An accountable role
   resolves policy exceptions; the researcher approves their own outputs and is responsible for
   the final submission. So a steward clears a referred action, and the project's owners still
   approve every document version and the deposit. A steward never approves on a researcher's
   behalf. A profile may add a check, never remove one: with `stewardship.deposit_co_approval:
   true`, a deposit also needs a `deposit_co_approved` event by a steward of the project's team,
   naming the package digest the researcher approved; a new package needs a new co-approval. A
   steward who is a member of the project may not clear its gates or co-approve its deposit,
   because the person checked would be checking themselves (C14). Not built yet,
   TODO(#374, #1306, #1308).

8. **A pause stops consequential steps until a steward lifts it** (P4, human on the loop). While
   a project is paused, the conductor refuses every run in it whose action class is not `advise`,
   and the harness refuses every deposit, each with the reason code `project_paused` and the
   pause's reason; the researcher can still read, converse with advisers, and write to the
   steward. A pause never lapses on its own: it is lifted only by the steward who applied it or a
   member of that steward's team. The researcher withdrawing the escalation does not lift it, and
   the team keeps access to the project until it is lifted. A run already in progress when the
   pause is applied finishes and is recorded. `project_paused` is a new value of the reason-code
   vocabulary, a fixed format: [Contract](contract.md) gains it in the pull request that builds
   pause. Not built yet, TODO(#374).

9. **The mandatory reviews stop their step until their reviewer acts.** The Blueprint makes these
   reviews compulsory; the profile's `stewardship.reviews` names, for each, whether the reviewer is
   the researcher, a steward or both, and the defaults are:

   | Trigger | Blueprint | Default reviewer | What stays stopped |
   |---|---|---|---|
   | The policy gate refers a run | §5.1, §5.4 | steward | the referred run |
   | A conflict between funder, journal and institutional requirements | R1, §5.1 | steward | repository choice and what depends on it |
   | Personal identifiers or sensitive information flagged | C2, §5.4 | researcher | the deposit |
   | Generic or low-quality metadata before submission | C15, §5.4 | researcher | the deposit |
   | Ethics approval or embargo not confirmed | R8, §5.2 | researcher | the deposit |

   A review that concludes data should not be shared, in whole or in part, is recorded as a valid
   outcome and ends that step (R8), not as a failure. Where no steward team is configured, a review
   whose reviewer is a steward falls to the researcher only if the profile says so; otherwise the
   step stays stopped with its card and the profile's contact (invariant 11). Built: the deposit's
   pause before packaging for the researcher's reviews ([Deposit](deposit.md)). Not built yet:
   the steward's reviews and the per-review profile key, TODO(#374, #16, #73).

10. **The researcher can see everything a steward does in their project.** The project's log view
    shows each `steward_viewed` (who and when), each steward action and each escalation's state,
    and a single status line answers "what is happening with my request?". A steward's message,
    proposed version and run are always labelled with the steward's name. Not built yet,
    TODO(#375, #376).

11. **A deployment without stewards still works** (C17). With no `stewardship` key, or no team
    for a project, the "Ask a data steward" control says so and shows the profile's contact if it
    has one, a referred step stays stopped with its card and its reason, and nothing else changes
    for the researcher. Not built yet, TODO(#375).

12. **A steward's contribution is attributed** (P5, R10). Each steward event maps to a
    `prov:Activity` associated with the steward as a `prov:Person` identified by their ORCID iD
    where they have one ([Provenance](provenance.md)), and carries a CRediT role: *Data curation*
    for a proposed edit, a run or a note, and *Validation* for clearing a gate, a review or a
    co-approval. In the deposit package's RO-Crate, a co-approval or a cleared gate is an
    `AssessAction` and a steward's accepted edit an `UpdateAction`, each naming the steward. A
    steward's read is not exported. Not built yet, TODO(#374).

## Boundaries and contracts

- **The harness decides; the shell renders.** Every check above is in `dd_harness`; the app's
  shell holds no policy ([The app](app.md)). Each project response gains `permitted_actions`, the
  actions the signed-in person may take there and why any is refused, so the shell shows only
  what is permitted and explains the rest, instead of learning its limits from a 403,
  TODO(#374). The session response names the person's deployment roles and teams (built).
- **Routes.** A steward's routes are under `/api/steward/` (the queue, the overviews) and the
  existing `/api/projects/{project_id}` routes, which serve a steward through the steward path of
  invariant 2. There is no separate copy of a project for stewards.
- **A steward's run** acts for the steward (`acting_for` is the steward's principal), never for
  the researcher, with the project as context, so the runs record and the provenance say who
  asked. Whether the run envelope records the role it was asked in is a contract change, made
  with #374.
- **Notifications** carry a link and a short subject, never research content or personal data
  beyond what is needed. The harness record stays authoritative wherever a notification goes,
  TODO(#378).
- **The admin service** stays the operators' loopback, read-only view, with no sign-in. A steward
  does not use it.

## Rationale

- **Roles in the profile.** The deployment owns policy, and the profile is already the reviewable,
  recorded place for it ([Policy and identity](policy-and-identity.md)). ORCID asserts no
  institutional role, so the first deployments must name stewards themselves; group claims can
  follow without a new mechanism.
- **Escalation-only by default.** A steward's view discloses a person's work (C2, P4). The
  Blueprint asks for override rights that are "role-based and governed, not open to all users"
  (§5.4). A deployment that wants stewards to monitor proactively can widen visibility to its
  supported projects, and every look is still recorded and shown.
- **Propose, not decide.** The workflow belongs to the researcher (§8), who approves their outputs
  (R2). A steward's authority is the institution's, over policy exceptions (§5.1), so the two are
  kept as separate records. This keeps the steward from becoming the bottleneck the tool exists to
  relieve (§3.1.1).
- **The log, not a new store.** An escalation is about a project and must sit in its history,
  provenance and access checks. A separate store would need its own access rules and backup.
- **Pause is a steward's, and never lapses.** The Blueprint's v2.0 "hold framework" (§13.1,
  Appendix G) asks for a hold that does not auto-resume; P4 asks for on-the-loop intervention. A
  pause that lapsed would let a step run that a person had stopped.
- **Discovery.** These decisions are to be checked with working research data management teams
  (#371) and the RDA working group, which names escalation and suspension the key community
  governance question (§13.1).

## Rejected alternatives

- **Roles from an environment variable**, as the workbench's `DD_WORKBENCH_ADMINS` once did. A role is a policy
  choice, which belongs in the profile and is recorded with every run.
- **Making a steward a project member.** A member decides facts and an owner approves; giving a
  steward either would blur whose decision a record shows, and membership is the researchers' to
  manage.
- **A role-assignment page in the app.** It would put policy in a second place, unreviewed and
  unrecorded with runs.
- **Every project visible to every steward by default.** It discloses researchers' work without a
  reason, and no Blueprint requirement asks for it.
- **A steward approving content or a deposit.** It contradicts R2 and §8, and makes the steward
  responsible for a submission they did not make.
- **An escalation store separate from the project log.** See Rationale.
- **An abstention raising an escalation automatically.** Stewards are scarce; the researcher
  decides whether a matter is worth a person's time.

## Non-functional requirements

- **Accessibility.** Every steward action and every escalation control works by keyboard and
  screen reader, and each state change is announced (#74).
- **Security.** A steward's access, each `steward_viewed`, each pause and each gate decision is
  also a security-log event ([Security baseline](security.md)). The steward path is the access
  control AC-3 and AC-6 rely on for deployment roles.
- **Scale.** A team's queue is one indexed query, like a person's project list ([Storage](storage.md)),
  and runs in the listing pool.
- **Personal data.** An escalation holds the researcher's note and the scope they chose to share,
  nothing more; it is kept and deleted with its project ([Projects](projects.md), invariant 22).

## Open questions

- Whether an escalation gets an AI first pass, summarising it for the steward, before a steward
  sees it (§13.2), TODO(#1310).
- Which team receives an escalation for a project shared across institutions, under an
  inter-institutional agreement (§5.1), TODO(#371).
- Whether an escalation can go to an institution's helpdesk, with the harness record kept
  authoritative, TODO(#378).
- Mapping identity-provider group claims to teams, TODO(#936).
- What happens to a project whose owners have all left, and whether a team may look after it,
  TODO(#1309).
- Cover, reassigning and transferring escalations between stewards and teams, TODO(#1308).
- The aggregate community and compliance overview (§4.1), TODO(#1307); the per-project team list,
  TODO(#232).
- Whether an unanswered escalation is routed again after the expected response time, TODO(#378).
