# The intake against §8

This is a reading of the project intake ([Orchestration](orchestration.md), invariant 20) against
the Blueprint's process flow ([§8](../blueprint/08-process-flow.md)), made for issue #670. It
checks the questions' wording, the entry points each is asked from, and the steps an answer marks
skipped. The questions are in `dd_sdk.intake`; the steps are in `dd_sdk.process_flow`.

It is a draft reading, prepared for a Blueprint reader to confirm. It records no review in
`docs/reviews.yaml`: that entry is made by the person who carried out the review.

## The questions

| Question | §8 decision point | Reading |
|---|---|---|
| `intake.entry` | The three entry points of §8.1. | Matches. The options use §8.1's wording. |
| `intake.dmp`, from entries 1 and 2 | Figure 1, "Does a Data Management Plan (DMP) exist?" (Phase 1, entry 1). "No" leads to creating a plan (optional), "Yes" to reviewing it. | The decision gates the steps that create and review a plan, `setup.dmp-create` and `setup.dmp-review`, each served by an alpha agent. Figure 2's check of data sharing against the plan (R8, `governance.dmp`) has no decision of its own, so skipping it on "No" was an inference, not a §8 branch. The answer now skips the branch not taken: "Yes" skips `setup.dmp-create` and "No" skips `setup.dmp-review`. Figure 1 joins both branches before Phase 2 and does not send a plan just created to review; this reading does, since a plan written here is one the researcher now has: once a version of it is approved, the "No" no longer skips `setup.dmp-review`, and the DMP Checker reviews that plan. The skip shows the branch not taken, and it does not bring Phase 1 into the tracker of a project that entered at Phase 2. The model orchestrator offers to write a plan on "No" and to review the plan on "Yes". Since creating a plan is optional in Figure 1 and so never the suggested step, "No" carries a notice saying that writing one is optional and still available. |
| `intake.sensitive`, from entries 1 and 2 | Figure 2, "Is sensitive data present?" (Phase 2). "No" continues without handling it; "Yes" anonymises or removes it. | Confirmed. "No" skips `governance.sensitive-data-identify` and `governance.sensitive-data-handle`. "Personal or otherwise" widens §8's wording to the personal data that §5.2 also covers. A "No" does not skip Figure 2's check of ethical, legal and institutional constraints, `governance.constraints`, which is a separate box after the branch. |
| `intake.repository-mandated`, from entries 1, 2 and 3 | Figure 3, "Is a repository mandated by funder, journal or institution?" "Yes" goes to "Use mandated repository" and bypasses "Find a suitable repository" (R1). "No" goes on to find one. | Confirmed with one correction. "No" still skips `repository.mandated`, the check the question answers. "Yes" now also skips `repository.recommend`, as §8's branch bypasses it. The "Use mandated repository" box has no step of its own. |

The entry points follow the phases each question's step lies in. Entries 1 and 2 reach Phase 2 and
entry 3 does not, which is why the first two decision questions are not asked at entry 3; all
three reach Phase 3. §8 assumes the governance checks are met before Phase 3, so a "No" to the
mandated-repository question is the researcher's word and may be reopened from the phase tracker.

## What is not asked

The intake asks at most three of §8's decision points. The others are left to the step that needs
them, when the researcher can see why: whether an embargo is required (Figure 2), whether the
repository assigns identifiers automatically (Figure 3), whether a data dictionary was created
before collection (Figure 4) and the two decisions about a related article (Figure 6).

## Decisions

1. **"Yes" to sensitive data says something at once.** The card says not to paste or upload the
   sensitive data itself into the conversation, and that the governance step covers its handling.
   §5.2 asks that sensitive data not reach the model without institutional authorisation, and
   Figure 2's note asks that it be anonymised first in a cloud deployment. The notice marks no
   step and does not depend on the deployment: whether the data may reach the agent at all is for
   the governance step.
2. **A deployment may not change or extend the question set in its profile.** The questions are
   Blueprint data, the same for every deployment. A deployment still shapes the conversation
   through the agents it enables. The implementer profiles of [§11](../blueprint/11-implementation-guidance.md)
   are not the deployment's policy profile.
3. **The Data Management Plan question marks no step done.** It skips the branch not taken, and a
   "Yes" now leads
   the orchestrator to invite the researcher to attach their plan, or to mark which attached
   document it is, so that the check against the plan reads it ([Projects](projects.md),
   invariant 32; #1447). Whether to keep the question is left to the Blueprint reader
   (TODO(#670)).
4. **"Yes" to a mandated repository skips `repository.recommend`.** No answer marks a step done.
5. **A model's suggested answer skips nothing.** An orchestrator's model may suggest an answer it
   read in the researcher's words, which the card shows chosen, but only the researcher's answer
   marks the steps in the table above, so the reading of each skip is unchanged
   ([Orchestration](orchestration.md), invariant 20; TODO(#908)).
