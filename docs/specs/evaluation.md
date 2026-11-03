# Evaluation and conformance

## Intent and scope

Two different questions are asked of Data Director, and each has its own machinery.

- **Conformance**: does the project meet a given Blueprint requirement? `CONFORMANCE.md` answers
  it per requirement, from the requirements register (`docs/requirements.yaml`), the review
  record (`docs/reviews.yaml`) and one test run. [The conformance report](../conformance.md)
  describes how to read it, claim a requirement with a test and record a review.
- **Evaluation**: how well does an agent do across many cases, and did a change make it worse?
  Evaluation runs on Inspect AI (always written in full, since the viewer also has a page called
  Inspect). It starts with seeded defects: take a known-good input, break it in one named way,
  and what the agent should then do follows from the defect.

The two never feed each other. A test that passes shows that one example path works; an
evaluation score measures quality over a case set; a review records what one person found
within a stated scope at one commit. None of these is a claim that a requirement is met in
general, and the report says so.

Only the standards advisor has an evaluation so far. Its labels are provisional: they follow
the Metadata Librarian's guidance in Uzwyshyn, *The Research Data Director* v0.8.2, and no domain
expert has reviewed them. A labelled corpus of real ORDA records is to replace them, as a second
dataset for the same task (TODO(#22)).

## Invariants

1. Every evaluation case goes through the conductor, so the policy gate, the input check and
   the grounding linter apply as they do to any invocation. The evaluation calls no model
   (`--model none`) and acts for whoever runs it. By default the agent is served in memory over
   A2A; given a registry of agent URLs, the same task reaches the deployed services.
2. What is common to every agent's evaluation (the solver, the scorers for outcome, stopping and
   grounding, the run comparison) lives in the workbench. An agent's cases, defects and own
   scorers live in its package. The workbench's `src/` imports no agent, and the harness imports
   no `inspect_ai` (`harness/tests/test_harness_boundary.py`).
3. Stopping is scored as an answer in its own right. `abstained`, `referred` and `suspended` are
   stops; stopping when the case expects an answer and answering when it expects a stop are
   counted separately; a `failed` run is neither and scores incorrect.
4. Scores are never blended into one figure. For the standards advisor, recall of the expected
   recommendations and "no wrong recommendation" are separate scores: a missed standard and a
   confidently wrong one are different failures.
5. A scorer that does not apply to a case returns NOANSWER, and the metric leaves that case out
   (`mean_applicable` in `workbench/src/workbench/evaluation.py`). Inspect AI's own `mean` would
   count it as zero, against the project rule that a missing input is `None`, never `0.0`.
6. A defect is a named function in a registry, and a registered name's behaviour never changes;
   a new mutation is a new name. Otherwise a baseline recorded against the name would silently
   measure something else. A defect copies its input and is deterministic
   (`agents/advisor-standards/tests/test_standards_evals.py`).
7. A run records what produced it: the git revision, the agent's configuration variables, its
   `AgentSpec.version`, and the hashes of the ranking rules, the snapshot and the case file. The
   hand-set version alone does not change when those inputs do.
8. Each evaluated agent commits a baseline of per-case scores and run identity. A pytest test
   reruns the evaluation and fails if any case scores lower, or higher, or if the identity
   hashes or agent version differ (`test_no_case_scores_below_the_committed_baseline`). The
   baseline is rewritten only by `workbench/scripts/eval_compare.py --write-baseline`, in a
   commit of its own that says which cases changed and why (enforced in review).
9. An evaluation test carries no `requirement` marker, and no evaluation result appears in
   `CONFORMANCE.md`. Nothing checks this mechanically; it holds by review.
10. A case names FAIRsharing records by identifier only. The snapshot is CC BY-SA 4.0, and
    copying record content into a case file would carry that licence onto it.
11. Each register entry names the lanes it is assessed in, `assessed_by`: `test`, `review` or
    both. Absent means `test` alone.
12. Each lane gives its own verdict from the same three words, *substantiated*, *contradicted*
    and *unsubstantiated*, in its own column, counted separately in the summary. The lanes are
    never combined into one verdict. A lane a requirement does not name reads *not assessed*.
13. The test lane is the traceability rule: substantiated if a test marked with the identifier
    passed and none failed or errored; contradicted if any failed or errored; otherwise
    unsubstantiated. A Blueprint row is not substantiated by its project sub-IDs.
14. A `requirement` marker must name a registered identifier whose lanes include `test`;
    collection fails otherwise (root `conftest.py`). A requirement that gains a meaningful test
    adds `test` to its lanes. A test is marked only if it exercises the requirement as the
    Blueprint states it.
15. The review lane reads the latest entry for the requirement in `docs/reviews.yaml` (on the
    same date, the later entry in the file): `meets` is substantiated, `does-not-meet`
    contradicted, no entry unsubstantiated.
16. A review is recorded by its reviewer, or on their written instruction, in a commit of its
    own, and is never edited; a new finding is a new entry, so the file is the history of
    reviews. Nobody, human or agent, writes a review on someone else's behalf without that
    instruction.
17. A malformed review record is a configuration error, not a verdict. The generator exits
    non-zero on a missing field, an unknown finding, a quoted date, a commit that is not a hash,
    or a requirement not registered for review, and never skips the entry
    (`scripts/conformance_report.py`, `load_reviews`).
18. `CONFORMANCE.md` is generated, never edited by hand, and holds only what the commit's own
    inputs decide. CI regenerates it from the test job's report and fails if a byte differs
    (`conformance` job in `.github/workflows/ci.yml`, `--check`); per-run facts (commit tested,
    time, Python version, counts) go to the job summary instead.

## Boundaries and contracts

- Evaluation depends on the harness's conductor and the agents' contract; it changes neither.
  Outcomes and reason codes are those of [the contract](contract.md); the linter verdict scored
  is the one [grounding](grounding.md) defines, and the human an evaluation acts for follows
  [policy and identity](policy-and-identity.md).
- `inspect-ai` is the workbench's `eval` extra, on the evaluation and CI path. Its fallback is a
  loop over the case file that calls the conductor and applies the scorers as plain functions;
  the scorers read only the envelope and linter report, and the comparison only per-case floats,
  so both port directly. Its tier is recorded in [dependencies](dependencies.md).
- The register lists every R and C requirement of Blueprint §7, whether or not anything here
  addresses it, plus project identifiers (R3.n, sub-IDs such as C13.1, `DD-*`) that the
  Blueprint does not use.
- The lanes and the review record's format are fixed: changing them changes this spec. Which
  lanes a requirement is assessed in is a register edit, made in review.
- The report is unsigned. What ties it to the code is the commit that contains it; a review is
  attested only by its entry and the signed-off commit that added it. Signing is deferred until
  the project has a release process ([dependencies](dependencies.md)).

## Rationale

- Inspect AI makes the evaluation runner mostly tasks and scorers rather than bespoke code, and
  its log is a browsable result.
- No labelled corpus and no community benchmark exist (Blueprint §10, C15). A seeded defect needs
  no labeller. The EnviSmart result, in which a producing role caught none of four seeded errors
  and an auditing role caught all four, is the case for starting here.
- Sending cases through the conductor measures the agent as it is governed in use, not a bare
  function that the gate or linter would have stopped.
- Failing on improvement as well as regression makes every change in behaviour visible in
  review, with the baseline commit saying why.
- Many requirements have no mechanical answer: whether a recommendation is appropriate (R3) or
  meets curation standards (C15) needs a domain expert; compliance (C3) and evidenced governance
  (C12) need someone who knows the obligations; security (C1) and sovereignty (C4) are properties
  of a deployment; automated checks find only some WCAG failures (C6); the pause for a human and
  the ethics prompt are checked by people (C2). With one test-based verdict, "nobody has written
  a test" and "no test could settle this" both read *unsubstantiated*, and a review actually done
  could not be recorded.
- A passing test and a failed review are different findings. Combining them would let one hide
  the other, the same reason evaluation scores stay apart.
- Most rows reading *unsubstantiated* is the honest default. The Blueprint's Appendix D records
  what implementers intend; the report records what a test run and the recorded reviews showed.

## Rejected alternatives

- **A blended evaluation score.** It hides which kind of failure moved.
- **Inspect AI's `mean` over all cases.** It scores an inapplicable case as zero.
- **Editing a defect in place.** It silently changes what an existing baseline measures.
- **Reporting evaluation results in `CONFORMANCE.md`, or marking evaluation tests.** A score
  over provisional seeded cases is not evidence that a requirement is met.
- **One combined verdict per requirement.** See rationale; a failed review must stay visible
  beside a passing test.
- **Skipping a malformed review entry with a warning.** A dropped review silently changes a
  verdict; failing CI makes the record fixed or removed.
- **Run-specific facts in the committed report.** They would make `--check` fail on every run of
  an unchanged commit.

## Non-functional requirements

- The evaluation and the conformance run need no network and no credentials; the evaluation
  runs inside the ordinary CI test job.
- Inspect AI leaves one memory stream unclosed. The evaluation test module ignores that single
  `ResourceWarning` and forces garbage collection at teardown, so the warning cannot fail an
  unrelated later test; the filter is scoped to that module so a leak elsewhere still fails.
- Seeded defects show only whether an agent responds to faults the project introduced. They say
  nothing about real deposits; the corpus is still needed (TODO(#22)).

## Open questions

- TODO(#248): whether a review should lapse, for example when files in its declared scope change
  after the reviewed commit. Until then a review holds until a later one supersedes it, and the
  report shows the reviewed commit so a reader can judge.
- TODO(#244): whether the app shell's tests feed `CONFORMANCE.md`.
- TODO(#7): evaluation and workshop materials for D4, including Exercise 4 ("Should it have
  stopped?"), which can build on the stopping score.
- TODO(#35, #42): how to benchmark Data Director beyond seeded defects, and evaluation of the
  guardrails.
