# advisor.rights

**Mock, alpha** (`0.1.0a1`): a placeholder for the Rights and Licensing Adviser persona
(ADR-0033). It gives no real advice.

The Rights and Licensing Adviser serves two steps of the Blueprint's process flow (§8.2):

| Step | What the mock does |
|---|---|
| `deposit.licence` | Lists data licences from a short fixed table that fit the reuse the researcher wants to allow, or only the licence they say is mandated. |
| `deposit.access` | Lists the access levels (open, embargoed, restricted, closed) with a fixed sentence on when each applies, restricted and closed first when the data are sensitive. |

The researcher chooses. The adviser never picks a licence or an access level.

## Input and output

`RightsContext` may give `reuse_wanted` (`any`, `attribution`, `share-alike` or
`non-commercial`), whether the data are `sensitive`, a `mandated_licence` as an SPDX identifier,
and whether they include `third_party_content`. With none of these the agent abstains with
`INSUFFICIENT_INPUT`.

`RightsOptions` holds `licences` (SPDX identifier, name, URL and a note), `access_levels`,
`questions` for the researcher (what reuse to allow, whether the data are sensitive, who to ask
about sensitive data and third-party rights) and `limitations`, stating what the mock does not do.

## How it decides

By fixed rules over `src/dd_agent_advisor_rights/licences.yaml`. It consults no source and calls
no model, so its grounding mode is `none` and it cites only its input.

## What it does not do

- It offers five licences (CC0-1.0, CC-BY-4.0, ODC-By-1.0, ODbL-1.0, CC-BY-NC-4.0) and reads no
  licence texts.
- It does not check what a funder, journal, institution or repository requires or offers.
- It does not judge whether the data are sensitive or who holds rights in them.
- It is not legal advice.

The real adviser, drawing on the SPDX licence list, funder mandates through `advisor.policy` and
the repository's licence options, is TODO(#359).
