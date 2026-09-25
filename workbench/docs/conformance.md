# The conformance report

[`CONFORMANCE.md`](../CONFORMANCE.md) lists every requirement the project tracks and shows
what has actually been demonstrated for each: by an automated test, by a person's review, or
not yet at all. It is generated; nobody edits it by hand.

## Why it exists

The Blueprint's Appendix D records what implementers *intend* to support. This report records
what a test run and the recorded reviews *showed*. A row with nothing behind it reads
*unsubstantiated*, and most rows do. That is the honest default, not a gap to hide.

## How a requirement is assessed

Each requirement is assessed in one or both of two lanes
([ADR-0014](adr/0014-assessment-lanes.md)):

- **By test.** An automated test exercises the requirement on every CI run. This suits a rule
  with a clear right answer, such as "a disabled agent is refused".
- **By review.** A named person examines the requirement and records what they found. This suits
  a matter of judgement or of deployment, such as whether a recommendation is appropriate,
  whether the interface meets WCAG, or where data is stored.

Some requirements need both. R3 is tested (the agent returns grounded recommendations) and
reviewed (an expert judges whether those recommendations are good).

Each lane gives its own verdict, in its own column. The two are never merged into one.

| Verdict | By test | By review |
|---|---|---|
| ✅ substantiated | A marked test passed and none failed. | The latest review found the requirement met. |
| ❌ contradicted | A marked test failed. | The latest review found it not met. |
| ⬜ unsubstantiated | No marked test, or only skipped ones. | No review recorded. |

A lane the requirement is not assessed in reads *not assessed*.

**Substantiated is not a conformance claim.** A passing test shows that one example path works.
A review shows what one person found, within the scope they describe, at one commit. Neither
shows that the requirement is met in general. Measuring quality across many cases is
evaluation, which is reported separately ([ADR-0013](adr/0013-evaluation.md)).

## The files

| File | What it holds | Who changes it |
|---|---|---|
| [`requirements.yaml`](requirements.yaml) | The register: every requirement, its source and `assessed_by`. | Contributors, in review. |
| [`reviews.yaml`](reviews.yaml) | The review record: one entry per review, never edited. | The reviewer, or someone on their written instruction. |
| Test markers | `@pytest.mark.requirement("<ID>")` on the tests that exercise a requirement. | Contributors. |
| [`../scripts/conformance_report.py`](../scripts/conformance_report.py) | Reads the three above and a test run, and writes the report. | Changes to its rules need an ADR. |
| [`../CONFORMANCE.md`](../CONFORMANCE.md) | The generated report. | Only the script. |

The register lists every functional (R) and non-functional (C) requirement in Blueprint §7,
whether or not anything here addresses it. `source: blueprint` rows use the Blueprint's own
identifiers; `source: project` rows (R3.1–R3.6, R4.1, R10.1, C5.1, C13.1, C13.2, C14.1, `DD-*`) are ones
this project introduced. A sub-ID such as C13.1 splits a Blueprint requirement so that a row
claims only what its tests show; its title says what is not exercised, and the Blueprint parent
stays unsubstantiated until the rest is.

## Claiming a requirement with a test

Mark the test with the identifier it exercises:

```python
@pytest.mark.requirement("R3.6")
def test_r3_abstention_reasons_are_distinct() -> None: ...
```

Collection fails if the identifier is not in the register, or if the register assesses it by
review only. Mark a test only if it exercises the requirement as the Blueprint states it. A test
that checks a slot exists (the P14 energy fields say `not_measured`) does not show that the
requirement is met, and is not marked. An evaluation test carries no marker at all.

## Recording a review

1. Check that the requirement's `assessed_by` includes `review`. If it does not, change the
   register first and say why in the pull request.
2. Carry out the review against a specific commit and write notes: what was examined, how, and
   what was found. Put the notes somewhere with a stable link, such as an issue.
3. Append an entry to `reviews.yaml`:

   ```yaml
   - requirement: C6
     verdict: does-not-meet
     reviewer: A. Reviewer (University of Example)
     date: 2026-10-01
     commit: 0123abc
     scope: The viewer's Inspect and Chat pages, tested against WCAG 2.1 AA with NVDA and
       keyboard only.
     record: https://github.com/data-director-agent/data-director/issues/0
   ```

   Every field is required. `verdict` is `meets` or `does-not-meet`. Write `date` unquoted.
4. Regenerate the report (below) and commit both files together, signed off (`git commit -s`),
   in a commit of their own.

A later review supersedes an earlier one; on the same date, the later entry in the file wins.
Never edit a recorded review: a new finding is a new entry. Only the reviewer records a review,
or someone acting on their written instruction.

A review stays current until a later one replaces it, however much the code changes. The report
shows the reviewed commit so that readers can judge. Whether a review should lapse automatically
is still to be decided (TODO in ADR-0014).

## Regenerating the report

From the repository root:

```sh
uv run pytest --json-report --json-report-file=workbench/.report.json
uv run python workbench/scripts/conformance_report.py
```

CI runs the same commands with `--check`. The check fails if the table differs from the
committed file, so a change that alters any verdict must commit the regenerated report. The
header, with its timestamp and commit, is left out of the comparison. The script exits with an
error if `reviews.yaml` is malformed, rather than skipping the bad entry.

## What the report does not do

- It is not signed. The commit hash in its header and the CI job are the only link between the
  table and the code (ADR-0006, "Rejected for v0").
- It does not score quality. That is evaluation (ADR-0013).
- It does not certify an instance. A deployment's security, sovereignty and compliance depend on
  how it is run, and a review records only what was examined.
