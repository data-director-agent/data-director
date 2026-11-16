# Personal data and disclosure control

## Intent and scope

A researcher adds an inventory of their dataset to a project instead of the data
([Projects](projects.md)). Today the inventory is safe because it holds no values: paths, sizes,
digests, formats and each table's field names and types. Two things are missing:

- nothing looks at whether the data hold personal data, so a clean inventory says nothing about
  it (#470);
- the Documentation Editor cannot infer a field's range or its missing-value codes (R5, #571),
  because a value-level summary can single out a person: a minimum age of 97 in a small cohort,
  or a category held by one participant.

This spec covers both, in `dd-inventory`, on the researcher's own computer, before anything leaves
it. It has three layers, each answering a different question:

1. **Minimise by design.** The inventory carries facts about files, never content
   ([Projects](projects.md), invariant 1).
2. **Detect direct identifiers** (e-mail addresses, telephone numbers, national identifiers,
   postcodes, names) in the values the command already samples, in field names and file names,
   and in small free-text files, and flag where they were found, never what (#470).
3. **Statistical disclosure control (SDC)** for summary values the command computes about a
   table's fields (#611), and a check for combinations of ordinary fields that single out a
   record, flagged for a person (#612).

C2 sets the boundary. The Data Director minimises what its outputs expose, flags possible
identifiers and refers them to a person, and never anonymises or de-identifies. SDC here applies
only to **summaries the Data Director computes**. Risk in the dataset itself is flagged and
referred, never fixed: the command never changes, coarsens or suppresses anything in the dataset.
Indirect identifiers are a Blueprint Future Consideration, and the quasi-identifier check is a
first, bounded answer to it, not a claim to cover them.

Out of scope: screening uploaded documentation (#473), embedded metadata in binary files (#787),
personal data in conversation text bound for a hosted model (#40), and personal data the app holds
about the people who use it (#156). The same detector and the same rules on findings are meant
to serve #473 and #787 when they are built.

Today `dd-inventory` does none of this yet: detection lands with #470 and #471, summary values
with #611, and the quasi-identifier check with #612. This spec is the design they build to.

## Threat model

- **Who sees an inventory.** Every member of the project; agents in the project, and any hosted
  model behind them, since `inventory` is the one class of project content a profile lets go to a
  hosted model by default ([Projects](projects.md), invariant 8); the operator of the deployment
  and its backups; and, once a package is deposited, the repository and the public, if the
  inventory or text drafted from it is published.
- **What an attacker may know.** A colleague, a participant's acquaintance or a journalist may
  know that a person took part, and some of their attributes: age, sex, where they live, the
  date of an event. The checks assume such knowledge of one or a few attributes per person, not
  linkage with a full outside register, which they do not model.
- **What is protected.** Values in the researcher's files. Findings and summaries are designed so
  that what reaches a project is safe to show to everyone above; the researcher sees them before
  the inventory is added, and may leave any out (#472).
- **What is not protected against.** A researcher who types a value into a field description,
  personal data in file or folder names that the researcher keeps after being told of it, and
  disclosure by differencing two inventories of the same data made with different thresholds or
  rows (ACRO's own linked-table warning applies; see Open questions).

## Invariants

1. **A finding never holds a value.** A personal-data finding records a kind, where it was found
   (a file, and a column or "field name", "file name" or "text"), the proportion of sampled
   values that matched as a band, a confidence band, the detector and its version, and the rows
   or characters examined. It never holds a matched value, any part of one, an offset into a
   file, a row number or an example. Enforced by a test that no sampled value, nor any token of
   four or more characters from one, appears anywhere in the serialised inventory (#470).
2. **Absent is not empty.** An inventory whose findings list is absent was made with no
   detector, by an older command, or in a runtime where detection does not run; an empty list
   means a detector ran and found nothing. Readers keep the two apart, and an inventory made
   before the change still validates and reads as "no detector ran" (#471). The same holds for a
   field's summary values and its disclosure check.
3. **Detection runs offline.** The command makes no network request to detect or summarise:
   no model download, no public-suffix list, no service. Enforced by the test suite's blocked
   network.
4. **Flag, never fix.** A finding is a prompt for a person. The command never rewrites,
   redacts, masks, coarsens or deletes anything in the dataset, and offers no "fix".
5. **A summary value that fails a rule is left out, not altered to pass.** The value is
   suppressed, the field's disclosure check counts it, and the value itself is kept nowhere.
6. **No raw extreme leaves the computer.** A range is never the raw minimum and maximum. Each
   bound is the *k*-th smallest or largest value, so at least *k* records lie at or beyond it,
   where *k* is the minimum frequency threshold (invariant 7).
7. **Every count passes the threshold before it is written.** A category, a missing-value code's
   count and a null count are each checked by ACRO's minimum-threshold rule with *k* = 10 by
   default, counts are rounded to base 5, and a zero count is treated as disclosive, as ACRO's
   defaults have it.
8. **The researcher may tighten, never relax.** The command accepts a higher *k* and a larger
   rounding base, and refuses lower ones. A deployment may require a higher minimum for the
   inventories its project store accepts (Open questions).
9. **Each check says what it did.** Every table field with summaries records its check: the
   rules applied, their parameters, the tool and its version, and how many values were
   suppressed. Never the suppressed values.
10. **A clean result is never presented as safe.** No wording, in the inventory, the command or
    the app, says or implies "no personal data", "safe" or "anonymous". The limitations say what
    was looked for and what was not (Wording for researchers).
11. **Quasi-identifier risk is referred, not decided.** A table in which some combination of the
    candidate columns picks out fewer than *k* records produces a finding of kind
    `quasi-identifier-combination`, which names the columns and the size of the smallest group as
    a band, and nothing else. What happens next is a person's decision (C2).

## Boundaries and contracts

**Where it runs.** All three layers run in `dd-inventory`, which depends on no other workspace
member ([System and boundaries](system.md)). The findings list, the per-field summaries and their
check are slots of the core `FileInventory` and `TableField`, a fixed format, so adding them
changes the [Contract](contract.md) and bumps the contract version as an additive change (#471,
#611). What the harness, agents and the app do with findings (the pause and the referral to a
data steward that C2 asks for, and hints to the ethics adviser) is #471's.

**The detector.** Microsoft [Presidio](https://github.com/microsoft/presidio) (`presidio-analyzer`)
is a required dependency of the command, behind one module, `dd_inventory.personal`, and a
`Detector` protocol, so that the comparison #39 asks for can replace it without touching the scan.
It is configured, not taken with its defaults:

- **No language model by default.** Presidio's default engine downloads `en_core_web_lg` if it is
  missing. The command builds its engine over a blank spaCy pipeline instead, so it uses
  Presidio's pattern, checksum and context recognisers only. A spaCy model cannot be a dependency
  of a package on PyPI (model wheels are published by URL), so name and location recognition
  runs only when the researcher names an installed spaCy model on the command line. Without one,
  the limitations say that names and places were not looked for in values.
- **No public-suffix download.** Presidio's e-mail recogniser calls `tldextract`, which fetches
  the public-suffix list on first use. The command replaces that recogniser with one that uses
  `tldextract`'s bundled snapshot only.
- **UK recognisers.** Presidio has the NHS number. The command adds the National Insurance
  number and the UK postcode, and leaves out recognisers for United States identifiers, which
  misread UK postcodes and National Insurance numbers as US driving licences. Which recognisers
  run is listed in the finding's detector string, so a reader knows what was looked for.
- **Field names and file names** are matched by a keyword table of the command's own, by
  category (direct identifier, contact, location, date of birth, health, and so on), copied from
  and kept in step with the ethics adviser's table, which the command may not import.

**What is scanned.** For a CSV or TSV table, the rows Frictionless samples to infer its fields
(1,000), column by column, and its field names; every file and folder name; and free-text files
of a few known suffixes (`.txt`, `.md`) under a size cap. Other formats are not
read, and the limitations say so.

**Thresholds for a finding.** A column is flagged when at least one sampled value matches a
recogniser at or above Presidio's score of 0.5, and the proportion and the highest score are
reported as bands. A lower score is not dropped: it is reported with a low confidence band, so a
person sees it (#39: below a threshold, refer rather than pass).

**Disclosure control.** [ACRO](https://github.com/AI-SDC/ACRO) (`acro`, the SACRO project's output
checker, MIT) is a required dependency, behind one module, `dd_inventory.summaries`, with its
quasi-identifier use in `dd_inventory.quasi`. ACRO checks outputs of an analysis on a pandas data
frame; the command uses it as follows, each call in suppression mode, in memory, with ACRO's
output folder in a temporary directory, never in the dataset, and its logging silenced:

| Summary | How it is computed | ACRO check |
|---|---|---|
| Categories of a field | A one-way frequency table (`crosstab`) of the field | Minimum threshold *k*; cells below it suppressed |
| Missing-value codes | Candidates (`-99`, `-999`, `999`, `9999`, `NA`, `N/A`, `.`, empty) found in the field, with their counts | Minimum threshold *k* on each count |
| Null count | Rows with no value | Minimum threshold *k*, rounded |
| Range of a numeric or date field | The *k*-th smallest and *k*-th largest values (invariant 6) | Minimum threshold on the count at or beyond each bound; ACRO's own min and max aggregates are not used, because ACRO passes a raw maximum as "ok" and only asks for a manual review against linked tables |
| Quasi-identifier combination | A cross-tabulation of the candidate columns | The number of cells below *k*, from ACRO's minimum-threshold check; the smallest non-empty cell, as a band |

Rows read for summaries and the quasi-identifier check are capped (100,000 by default), and the
limitations say when the cap was reached, since a sample is not the population.

**Candidate quasi-identifier columns** are those whose name or inferred type indicates age or a
date of birth, another date, sex or gender, geography (postcode district, area code, region),
occupation or ethnicity, and categorical fields with a rare category, at most four at once,
chosen in a fixed order so that two runs over the same data pick the same columns. A table with
fewer than two candidates is not checked, and the limitations say so.

**Bands.** Proportions and group sizes are reported as bands (`1`, `2 to 4`, `5 to 9`, `10 or
more` for group sizes; `under 1%`, `1 to 10%`, `10 to 50%`, `over 50%` for proportions), not as
numbers, so that a finding cannot be differenced into a count.

**The browser scanner.** spaCy and ACRO do not run under Pyodide. Where the command detects that
runtime, it runs neither detection nor summaries, leaves both slots absent (invariant 2), and says
so in the limitations. When #367 builds the browser scanner, it installs the package without
these dependencies.

## Wording for researchers

What the command and the app say about a result, in substance:

- **Findings:** "Possible personal data was found in these places. The inventory does not
  include the values. Check them before you add the inventory, and talk to your data steward or
  ethics contact about how they should be handled. Data Director does not change your files."
- **No findings:** "No direct identifiers were found in the rows and names that were checked.
  This does not mean the data hold no personal data: free text beyond the files listed, other
  formats, indirect identifiers and rows beyond the sample were not checked."
- **Suppressed summaries:** "Some summary values were left out because fewer than *k* records
  shared them. They are not stored anywhere."

The app's wording, and the next steps C2 asks for, are #471's; this is the substance they keep.

## Rationale

- **Local, before it leaves.** Sending data to a service to check it for personal data defeats
  the purpose (P10, C4). The command already runs where the data are and reads a sample of each
  table, so detection and SDC cost one more pass over rows already read.
- **Presidio required, not optional.** A detector that most researchers do not install protects
  nobody, and a clean inventory from a command without one would look the same as a clean one
  from a command with one. Making it required keeps one meaning for "the detector ran". The
  price is a larger `uvx` install, recorded in [Dependencies](dependencies.md).
- **ACRO for the rules.** Output checking is a discipline with its own literature and errors.
  ACRO encodes the rules that trusted research environments use (threshold, dominance, p-ratio,
  rounding, zeros), is maintained by the SACRO project and is MIT licensed. Using it means the
  thresholds and their names are those a data steward already knows. The one rule of our own is
  the range bound (invariant 6), because ACRO does not check an extreme value.
- **Suppress, never perturb.** A perturbed or rounded-to-pass value is a value nobody observed,
  and a researcher drafting a data dictionary from it would publish something untrue.
  Suppression keeps what is shown true, and says how much is missing.
- **Bands, not counts, in findings**, so that the record of a check cannot itself be used to
  recover a small count.

## Rejected alternatives

- **A rule set written in this repository.** Lighter, and it would run in the browser, but it
  would be one more bespoke implementation of rules that ACRO already maintains, and stewards
  would have to trust our reading of the output-checking guidance rather than a tool they know.
- **sdcMicro and sdcTable.** The reference tools for SDC, with k-anonymity and risk measures
  ACRO lacks, but they are R packages: they would add an R runtime to a command meant to run
  with one `uvx` line.
- **Presidio as an optional extra.** Keeps the command light, but splits the meaning of a clean
  inventory between those who installed it and those who did not (Rationale).
- **Presidio's defaults.** They download a large spaCy model on first use and fetch the public
  suffix list, both network calls from a researcher's computer during a scan.
- **Storing matched values under protection.** #39 allows storing a value "under the same
  protection as the source". The inventory goes to a shared project and may go to a hosted
  model, so it has no such protection, and a value is never stored.
- **Raw minimum and maximum with a warning.** A warning travels less far than the value.

## Non-functional requirements

- **Privacy.** Invariants 1, 5, 6 and 9 keep values out of the inventory; the no-leak test
  enforces invariant 1 on a synthetic corpus.
- **Evaluation.** A synthetic corpus of tables and files, with no real personal data, labels
  what should be flagged, suppressed or referred (`inventory/tests/data/disclosure/`, #610).
  Catch rate and false alarms are reported separately for each kind of risk, as
  [Evaluation and conformance](evaluation.md) does for other scores, and are not a pass mark.
- **Performance.** Detection and summaries run on capped rows; on a laptop, a table adds seconds,
  not minutes. Recall by kind, false alarms on ordinary metadata and CPU time are reported with
  the corpus (#39).
- **Portability.** Native runs only; see the browser scanner above.

## Open questions

- Which detector #39's comparison confirms or replaces behind the same interface, TODO(#39).
- Whether a deployment's profile may require a higher *k* for the inventories its project store
  accepts, and whether the harness re-checks a received inventory's disclosure record against
  it, TODO(#471).
- Differencing between two scans of the same data (a revised inventory, or parts), which ACRO's
  linked-table check warns of and the command does not yet guard against, TODO(#611).
- How the browser scanner (#367) gets detection, if it ever does: a WebAssembly build of the
  recognisers, or none, TODO(#367).
