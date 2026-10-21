# ADR-0014: Requirements assessed by test, by human review, or both

**Status:** Accepted
**Date:** 2026-09-25

## Context

`CONFORMANCE.md` gave every requirement one verdict, computed by the traceability rule from the
tests that carry its identifier. The rule works for a requirement with a mechanical answer. "A
disabled agent is refused" (DD-POLICY) either holds or it does not, and a test checks it on
every commit.

Many Blueprint requirements have no mechanical answer:

- whether a recommendation is *appropriate* (R3) or an output meets curation standards (C15)
  needs a domain expert;
- compliance with funder, legal and institutional obligations (C3) and evidenced governance
  (C12) need someone who knows those obligations;
- encryption at rest, a NIST baseline (C1) and jurisdiction of storage (C4) depend on how an
  instance is deployed, not on a code path;
- automated accessibility checkers find only some WCAG failures; the rest need a person using
  a keyboard and a screen reader (C6).

For these the report rendered *unsubstantiated* whether nobody had yet written a test or no test
could ever settle the matter. Those are different states. A reader could not tell them apart, and
a contributor could not record a review that had in fact been done.

Evaluation (ADR-0013) measures agent quality over many cases, but it is not conformance and does
not appear in the report. Nothing here changes that.

## Decision

1. **Each requirement names how it is assessed.** An entry in `docs/requirements.yaml` may carry
   `assessed_by`, a list of one or both of `test` and `review`. Absent means `[test]`, so
   existing entries keep their meaning.
2. **Each assessment is a lane with its own verdict.** The lanes use the same three words:
   *substantiated*, *contradicted* and *unsubstantiated*. The report shows the two verdicts in
   separate columns and counts them separately in the summary. They are never combined into one
   verdict, for the reason ADR-0013 keeps scores apart: a passing test and a failed review are
   different findings, and one must not hide the other. A lane a requirement does not name reads
   *not assessed*.
3. **The test lane is the traceability rule, unchanged.**
4. **The review lane reads `docs/reviews.yaml`.** An entry names the requirement, the finding
   (`meets` or `does-not-meet`), the reviewer, the date, the commit reviewed, the scope of the
   review and a link to the reviewer's notes. Every field is required. The latest entry for a
   requirement gives its verdict: `meets` is substantiated and `does-not-meet` is contradicted.
   With no entry, the lane is unsubstantiated.
5. **A review is recorded by its reviewer and never edited.** An entry is added by the person
   who did the review, or on their written instruction, in a commit of its own. A new finding is
   a new entry, so the file is the history of reviews.
6. **A malformed record is a configuration error.** The report generator refuses an entry with a
   missing field, an unknown finding, a quoted date, a commit that is not a hash, or a
   requirement not registered with `review`. It exits non-zero, so CI fails, rather than skipping
   the entry.
7. **A test may not claim a review-only requirement.** The root `conftest.py` rejects a
   `requirement` marker naming an identifier whose `assessed_by` omits `test`. A requirement
   that gains a meaningful test adds `test` to its lanes.
8. **The initial assignment** is below. It follows the Blueprint's own text (§7) and can be
   changed by editing the register; the lanes and the review format cannot be changed without an
   ADR.

   | Requirement | Lanes | Why review |
   |---|---|---|
   | R3 | test, review | Whether a recommendation is appropriate is a domain expert's judgement. |
   | C1 | review | Encryption, access control and the NIST baseline are properties of a deployment. |
   | C2 | test, review | The pause for a human reviewer and the ethics prompt are checked by people. |
   | C3 | review | Compliance with legal, funder and institutional obligations. |
   | C4 | review | Where data is stored and processed is a property of a deployment. |
   | C6 | test, review | Automated checks find only some WCAG 2.1 failures. |
   | C12 | test, review | Governance compliance "must be evidenced" against recognised standards. |
   | C15 | test, review | Curation standards; the Blueprint makes human review mandatory. |

## Dependencies introduced

None. The review record is YAML read with PyYAML, which the report already uses.

## Consequences

- The report distinguishes "not yet tested" from "needs a person", and shows who reviewed what
  and at which commit.
- No review has been recorded. Every review lane starts *unsubstantiated*, and a reader sees
  which requirements are waiting for one.
- R3 and C15 keep their test verdicts; the added review column does not downgrade them.
- A review holds until a later review supersedes it, however much the code has changed since.
  The report shows the reviewed commit so a reader can judge. TODO: decide whether a review
  should lapse, for example when files in a declared scope change after the reviewed commit.
- The review record is unsigned, as the report is (ADR-0006, "Rejected for v0"). Its only
  attestation is the commit that added the entry and the project's DCO sign-off.
- Do not record a review for someone else without their written instruction. Do not edit a
  recorded review. Do not combine the two verdicts into one figure.
