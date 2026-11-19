# Preparing the JOSS paper

This page gathers what we need to know and collect before writing a paper about the Data Director
for the [Journal of Open Source Software](https://joss.theoj.org/) (JOSS). It holds no paper text.
It is tracked in [#1222](https://github.com/data-director-agent/data-director/issues/1222).

The JOSS rules below were read on 19 November 2026 from the
[submission guidelines](https://joss.readthedocs.io/en/latest/submitting.html), the
[paper format](https://joss.readthedocs.io/en/latest/paper.html) and the
[review criteria](https://joss.readthedocs.io/en/latest/review_criteria.html). JOSS changes its
rules, and its AI policy is recent, so read all three again before submitting and update this page
where they differ.

## How JOSS works

JOSS reviews the software, and the paper is a short description of it. It charges authors nothing.

1. You submit through the JOSS site. An editor-in-chief runs a pre-review check, and a handling
   editor then assigns two or more reviewers.
2. Review is open and iterative, in an issue in the `joss-reviews` repository. Reviewers install the
   software, check its functionality, tests and documentation, and read the paper. Authors answer
   in the issue.
3. Authors should reply to comments within about two weeks and finish requested changes within four
   to six weeks, unless the editor agrees otherwise. Long silence can lead to rejection.
4. After a successful review the authors make a tagged release, archive it (Zenodo or figshare) to
   obtain a DOI and report both in the review issue. JOSS then deposits the metadata with Crossref
   and announces the paper.

A reviewer grades the submission accept, minor revisions or major revisions. Major revisions are
not a rejection. JOSS does not say how long a review takes overall.

## Eligibility and pre-review gates

A submission that fails a gate is rejected before review. It can be resubmitted once the gap is
closed, which JOSS says can take six months or more. The status column is what the repository
shows today, with "unknown" where I could not check.

| Rule | Status | What to do |
|---|---|---|
| An OSI-approved licence file is in the repository. A mention in the README is not enough. | Met: `LICENSE` (MIT, per `CITATION.cff`). | Nothing. |
| The code is hosted where anyone can browse it, read and file issues, and propose changes without approval or payment. | Met, assuming the repository is public. | Confirm the repository and its issue tracker are open without an account. |
| The software has an obvious research application, and the paper does not report new research results made with it. | Likely met: research data stewardship. | State the research application plainly in the paper. Keep evaluation results for a separate paper. |
| It is not a thin API client, a single-function or minor utility package, a notebook or a pre-trained model. | Likely met: a multi-package system with a harness, agents and an app. | Say in the paper why it is more than a wrapper around a hosted model. |
| It is feature-complete and packaged to the norms of its language. | Unknown. Releases are all alpha (the latest, on 7 November 2026, is `app-v0.3.0-alpha.8`). | Decide what "complete" means for a first release, and tag a beta or 1.0 before submitting. |
| **The repository has been public for more than six months, with steady activity across that time.** Work concentrated in days or weeks is not accepted. | **Unknown.** The first commit on GitHub falls between 27 and 31 July 2026, so six months is not reached before the end of January 2027 at the earliest. The date the repository became public is not known here. | Confirm the public date, and if it was private first, when real use started. The pace of about 1,200 pull requests in about four months could be read as a burst, so show steady work through December and January. |
| **There is evidence of research use**, at minimum by the developers: citations, adoption by other groups, or integration into research workflows. | **Gap.** I found no outside users or pilots. | See [Research impact evidence](#research-impact-evidence). |
| Multi-author projects show issues, pull requests and discussion. Single-author projects show several of: commit history, tagged releases or a changelog, tests and CI, documentation, a CONTRIBUTING file, and a statement of support or governance. | Mostly met: CI, coverage, documentation, `CONTRIBUTING.md`, changelogs, governance and a charter exist. The sampled issues were all opened by one person. | Invite outside engagement in public. Non-author issues and pull requests are a positive signal. |
| The history shows ongoing refinement, not one burst of commits. | Unknown. | Check the history by month before submitting. |

## The paper

### Format

- The paper is Markdown in a file named `paper.md`, with a YAML block at the top and a `paper.bib`
  file for references. Both, and any figures, are in the same Git repository as the software.
  The paper may be on a short-lived branch, but it must be made from the default branch so that it
  includes the code.
- The YAML block has a `title` (plain text: no backticks around software names), `authors`, each
  with a name, an `affiliation` index and usually an ORCID iD, `affiliations`, each with an `index`
  and a `name` and optionally a `ror` identifier, and a `date` such as `19 November 2026`.
  The example paper that the JOSS guide links to is the template.
- Cite with `[@key]`, or `@key` in running text. Give full venue names, not abbreviations.
- A figure is an image with a caption, alone in its paragraph. Tables, equations and cross-references
  are supported. See the paper format page for the syntax.
- **Length is 750 to 1,750 words.** A much longer paper may be asked to shorten. API documentation
  belongs in the software's documentation, not the paper.
- Preview it by running the Open Journals PDF GitHub Action on the repository, or with the
  `openjournals/inara` Docker image with `JOURNAL=joss`.

### Where it will live

The plan is a `paper/` directory at the repository root holding `paper.md`, `paper.bib` and figures.
Adding it needs two checks first: the docs build fails on a tracked Markdown file that is neither in
the nav nor listed in `UNPUBLISHED` in `docs/hooks.py`, and `scripts/check_members.py` checks the
repository's members. Settle both when the directory is added.

### Required sections

JOSS's review criteria require each of the following. The material column lists where the
information is likely to come from in this repository. It is a starting point, not a claim that
the text exists.

| Section | What JOSS expects | Material to draw on | Still missing |
|---|---|---|---|
| Summary | What the software does, for a non-specialist reader. | [README](../../../README.md), [Architecture](../../../docs/architecture.md) section 1. | A plain description of the problem for someone outside research data management. |
| Statement of need | The problem, who the software is for, and how it relates to other work. | The [Blueprint](https://doi.org/10.15497/RDA00157) and its [community consultation](https://doi.org/10.15497/RDA00151). | The target audience in one sentence, with evidence of demand. |
| State of the field | What else exists, and a "build vs. contribute" argument if related tools exist. | The README's related-work list. | A survey of related tools. **To be researched, not assumed**: which tools do data stewardship, metadata drafting and repository selection, and why not extend one of them. |
| Software design | The design, its trade-offs and the reasons for them. JOSS rejects a generic description of code structure. | [Working in the repository](../../../AGENTS.md) rules 1 and 2 (formats decided, components behind interfaces, own the governance), [Dependencies](../../../docs/specs/dependencies.md), [Contract](../../../docs/contract.md), the harness's policy gate and grounding linter. | The trade-offs named explicitly: what was chosen, what was rejected and why. |
| Research impact statement | Realised impact, or credible near-term significance, with concrete evidence rather than aspiration. | Conformance to the Blueprint ([`CONFORMANCE.md`](../../../CONFORMANCE.md)), evaluations ([Evaluation and conformance](../../../docs/specs/evaluation.md)). | See [Research impact evidence](#research-impact-evidence). |
| AI usage disclosure | Whether generative AI was used for the software, documentation or paper, how, and how correctness was checked. | See [AI usage disclosure](#ai-usage-disclosure). | Versions and dates of use. |
| Acknowledgements and references | Funding, contributors, and key references including the archived software. | README acknowledgements, `CITATION.cff` references. | Funding statements, and whether the funders were involved in the work. |

Every reference needs its full venue name. Generated references are unreliable, so check each
against the original source, as the [AI usage statement](https://github.com/data-director-agent/.github/blob/main/AI_USAGE.md)
already requires.

## Research impact evidence

This is the most likely weak point. JOSS asks for evidence of research use, and a reviewer will
flag aspiration without evidence. Collect, with a link or a date for each:

- [ ] A pilot or deployment outside the maintainers' group, even a small one. The README mentions
  working-group discussions and a possible joint Sheffield and Oxford implementation.
- [ ] Citations of the software or its Zenodo record. `CITATION.cff` carries a DOI.
- [ ] Use in an RDA working-group activity, workshop or training session.
- [ ] Talks, posters or a preprint about the software.
- [ ] Issues, pull requests or discussions from people outside the maintainers.
- [ ] Reuse of the packages by others, such as the SDK or the inventory tool.

The evaluation of the agents' advice is research in its own right. JOSS does not allow the paper to
focus on new research results, so write that up as a separate paper and cite it.

## AI usage disclosure

JOSS permits generative AI for code, documentation and the paper, but every use must be disclosed
in an "AI usage disclosure" section. It covers:

1. the tools and versions used, and where they were used (code, paper, documentation);
2. the nature and scope of the assistance;
3. confirmation that people reviewed and validated the output and made the core design decisions.

JOSS may treat an incomplete or inaccurate disclosure as an ethical breach, with desk rejection,
mandatory revision or withdrawal. AI may not be used for conversations between authors and editors
or reviewers, except for translation.

The project's [AI usage statement](https://github.com/data-director-agent/.github/blob/main/AI_USAGE.md)
already answers most of this, and the disclosure should agree with it:

| JOSS element | Source in the AI usage statement | Gap |
|---|---|---|
| Tools and versions | Chiefly Claude Code. The model names are in the `Co-Authored-By` trailers, which can be counted with the `git log` commands in the statement. | The agent's own version and the exact date of each use are not recorded beyond the commit date. |
| Scope | Code, tests, documentation, specifications, issue and pull request text, and configuration. "A substantial part" has been drafted this way. | The statement does not give proportions. Decide whether the paper should. |
| Human review and design decisions | People decide what to build, record design decisions, review every change and answer for what is merged. | The paper should say which decisions were human, with examples from the RFCs and specifications. |
| What AI was not used for | Research findings, evaluation results and data. | None. |
| Prompts | Not retained in full. | Open as [#380](https://github.com/data-director-agent/data-director/issues/380). JOSS does not require prompts, but a reviewer may ask. |

Whatever AI helps to write the paper itself must be added to the disclosure too. Count it
separately from the software.

## Authorship and declarations

- JOSS asks that the submitting author is a major contributor, judged partly from commit history.
  Active project direction and non-code contributions count. Purely financial or general
  supervisory contributions do not. Every author must agree to be listed and be accountable for the
  work.
- `CITATION.cff` lists three authors. Agree which of them meet the test, and who else does,
  before the paper is drafted. AI assistants are not authors. They are disclosed instead.
- Declare financial, personal or professional conflicts of interest at submission, and acknowledge
  funding and whether the funder was involved.
- Say whether related publications exist, whether published, in review or nearly ready, such as a
  preprint or the evaluation paper.
- A preprint may be posted at any stage and does not count as prior publication.

## Readiness checklist

Fill in the owner column when each item is taken on.

| Item | Owner | Done |
|---|---|---|
| Confirm when the repository became public and when real use began. | | |
| Review the commit history by month for steadiness. | | |
| Tag a beta or 1.0 release, and archive it on Zenodo. | | |
| Decide the authors and check each against JOSS's authorship test. | | |
| Collect research impact evidence. | | |
| Survey related tools for the state-of-the-field section. | | |
| Write down the design trade-offs, with the RFCs and specifications that record them. | | |
| Settle the AI usage disclosure and decide on #380. | | |
| Add `paper/` and preview the PDF with the Open Journals Action. | | |
| Re-read the JOSS rules and update this page. | | |
| Draft `paper.md` and `paper.bib` within 750 to 1,750 words. | | |
| Submit, then answer reviewers within two weeks. | | |

## Timing

If the repository was public from its first commit, the six-month threshold is reached around the
end of January 2027. Submitting before the evidence and the release are in place risks a rejection
that takes months to recover from, so the gaps above, not the date, set the timing.

## Open questions

- When did the repository become public?
- Is there a pilot or other outside use that the paper can cite?
- Which people are authors?
- Is a beta or 1.0 release planned before submission?
- Should the evaluation of the agents' advice be a separate paper, and where?
- Should the disclosure rely on the commit history alone, or should model versions and dates be
  recorded from now on (#380)?
