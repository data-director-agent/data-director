# advisor.rights

**Model-backed alpha** (`0.2.0a1`): the Rights and Licensing Adviser persona
([Agents](../../docs/specs/agents.md)). It lists options from a short fixed table and gives no
legal advice.

The Rights and Licensing Adviser serves two steps of the Blueprint's process flow (§8.2):

| Step | What it does |
|---|---|
| `deposit.licence` | Lists data licences from a short fixed table that fit the reuse the researcher wants to allow, or only the licence they say is mandated. |
| `deposit.access` | Lists the access levels (open, embargoed, restricted, closed) with a fixed sentence on when each applies, restricted and closed first when the data are sensitive. |

The researcher chooses. The adviser never picks a licence or an access level.

## Input and output

`RightsContext` may give `reuse_wanted` (in the researcher's own words, or one of `any`,
`attribution`, `share-alike` or `non-commercial`), whether the data are `sensitive`, a
`mandated_licence` as an SPDX identifier, and whether they include `third_party_content`. With
none of these the agent abstains with `INSUFFICIENT_INPUT`.

`RightsOptions` holds:

- `licences`: SPDX identifier, name, URL and a note for each one;
- `access_levels`;
- `questions` for the researcher: what reuse to allow, whether the data are sensitive, and who to
  ask about sensitive data and third-party rights;
- `limitations`;
- `dropped`: what a model replied that was not used, and why.

Each licence and question records in `derivation` whether it came by rule (`template`) or from a
model's reading (`model`).

## How it decides

Rules first, over `src/dd_agent_advisor_rights/licences.yaml`:

- A `reuse_wanted` that is one of the table's values selects the licences that fit it.
- A mandated licence is the only one listed.
- The access levels and the fixed questions follow from what the researcher said.

What the rules cannot read goes to an interpreter (`interpret.py`), chosen by
`DD_RIGHTS_INTERPRETER` (`factory.py`):

- `template` (the default) proposes nothing. A reuse wish in other words falls back to listing
  every licence and asking what reuse to allow. It calls no model and needs no key.
- `model` sends the model the researcher's words for the reuse wanted (only when the rules did not
  understand them), the mandated licence, whether there is third-party content, and the table's
  licence ids, names and reuse values. Whether the data are sensitive is not sent. The model
  replies against a schema (`RightsReply`):
  - the table's reuse values that the words fit;
  - the order in which to offer the licences that fit;
  - up to three questions about the third-party content or the mandate.

A model's reply is checked against a closed set (`check`). A reuse value the table does not have,
a licence that is not among those that fit, or a question asked where there is neither
third-party content nor a mandate is dropped and listed in `dropped`. A licence the model names
from outside the table therefore cannot reach the payload. A licence that fits is never left out:
any the model does not order follow in the table's order. A mandated licence is still listed by
rule. When the model reads the reuse wanted, a question asks the researcher to check that reading.

A refused reply, a reply that is not the schema's JSON, or a model that cannot be reached leaves
the rules' result. The outcome's statement says so.

It reads only its input, so its grounding mode is `input_only` and it cites only its input.

## What it does not do

- It offers five licences (CC0-1.0, CC-BY-4.0, ODC-By-1.0, ODbL-1.0, CC-BY-NC-4.0) and reads no
  licence texts. Drawing them from the SPDX licence list through the harness's tool gateway, with
  a `licence-choice` Skill, is TODO(#877). The interpreter and its closed-set check stay, and the
  closed set becomes the records the gateway returned.
- It does not check what a funder, journal, institution or repository requires or offers. The
  repository's licence options and an evaluation set are TODO(#702).
- It does not judge whether the data are sensitive or who holds rights in them.
- It has no evaluation set yet, so how often the model misreads a wish is not measured.
- It is not legal advice.
