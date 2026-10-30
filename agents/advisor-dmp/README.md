# advisor.dmp

**Mock, alpha** (`0.1.0a1`). It gives no real advice: it compares two lists it is given. The
real checker is TODO(#356).

The Data Management Plan Checker is one persona of the agent roster (ADR-0033). It serves one
step of the Blueprint's process flow:

| Step | What the mock does |
|---|---|
| `governance.dmp` (R8) | Compares what the data management plan committed to share with what is planned at publication, and lists each difference for a person to review. |

R8 asks that sharing at publication be checked against the plan's commitments, with
discrepancies flagged for human review and never enforced. A reviewed decision not to share is a
valid outcome, and the checker says so.

## Input and output

`DmpCommitments` gives the plan's identifier, if any, and two lists of `SharingCommitment`:
`committed_outputs` (what the plan committed to) and `planned_outputs` (what is planned now).
Each names an `output` and may give its `repository`, `access` (such as open, restricted or
closed) and `licence`.

`DmpDiscrepancies` holds `discrepancies`, each with the `output`, the `aspect` that differs, what
was `committed` and `planned`, and a `message`; and `limitations`, what the mock does not do.

## How it decides

- Outputs are matched by name, case and surrounding spaces ignored.
- An output committed but not planned is `missing`; one planned but not committed is
  `unplanned`.
- For an output on both lists, `repository`, `access` and `licence` are compared as text where
  both sides give them, and each difference is listed.
- It abstains with `insufficient_input` when no committed outputs are given.

It consults no source and calls no model, so its grounding mode is `none` and it cites only its
input.

## What it does not do

- It reads no data management plan. The real checker will read machine-actionable plans in the
  RDA DMP Common Standard (see #284). TODO(#356)
- An output renamed since the plan is reported as both missing and unplanned.
- Two names for the same repository or licence count as different.
- It does not check timing, embargoes, costs, metadata standards or any other commitment.
