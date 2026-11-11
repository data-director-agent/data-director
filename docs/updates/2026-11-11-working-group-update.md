# Data Director: development update, 27 October to 11 November 2026

*For the RDA Data Director Working Group forum*

Dear colleagues,

Here is a plain-language summary of what has changed in the Data Director reference implementation over the last two weeks (around 300 changes in total). You do not need technical knowledge to follow it. The short version: **the tool now takes a researcher from "here are my files" to "here is a checked package, ready to deposit"**, with a person approving each step.

## The big picture

At the end of October, the Data Director could chat with you and offer advice (for example, which standards or repositories might suit your data). It could not yet *produce* much. It now works through a complete, if basic, loop:

1. **Describe your files.** You make or attach an "inventory", a list of your files and their structure. It describes your data but does not upload it. You can check it and leave out anything you do not want included.
2. **Start a project.** Each dataset lives in its own project, which holds the files' description, the documents drafted, and the decisions made. You can name and rename projects, and work in one at a time.
3. **Draft the documents.** The tool drafts a metadata record, a README and a data dictionary. Wherever it cannot know something (your methods, what a column means, its units), it leaves a clearly marked gap and **asks you**, usually as simple clickable choices or one question at a time.
4. **Review and approve.** Nothing becomes part of the project until you approve, edit or reject it. Each data dictionary value is marked as *inferred*, *supplied by you* or *unknown*, so you can see where it came from.
5. **Choose a repository.** The repository advisor now searches the whole of the re3data registry, ranks repositories by subject and by your country, and shows what your chosen repository requires.
6. **Validate and download.** The tool checks the project against the repository's requirements and builds a deposit-ready package, then tells you what to do next to upload it.

## Being open about AI

Because this is a tool for stewardship, we have put trust and transparency first:

- Every approved document **discloses the generative AI that helped draft it**.
- Project documents are **not sent to externally hosted AI models** unless an institution's policy explicitly allows it.
- The app says plainly what each agent is *given*, and a new **Policy page** shows the rules a run is held to.
- Each person sees **only their own** conversations and projects. We also closed several security gaps, including one where one user could read another's tasks.
- You can now sign in with **ORCID**, and optionally let the tool use facts from your public ORCID record, such as your name and affiliation, when drafting.

## Easier to use

The app has been simplified for non-specialists: a Projects page comes first, the stages are shown as a plain-language "data journey", earlier conversations have readable titles, documents can be browsed in a list and a reader, and you can attach a supporting document to a message. There is also an in-app link to the user guide on every page, and a problem-reporting route.

## Behind the scenes

For those running the system at an institution: configuration is simpler (a single setup tool with a self-check), production container images are now built automatically, and there is a backup, restore and monitoring setup for stored projects. A first Python package for creating inventories is published for testing. Documentation grew to match, including a first-contribution guide and a decisions log.

## What this is *not* yet

We would rather be clear about the limits:

- **It remains alpha software.** Expect change, rough edges and bugs.
- **Several advisors are still mock-ups**, showing the intended behaviour but with simple rules rather than real analysis: ethics, files, data management plan comparison, FAIRness, rights and linking, plus the first-draft metadata record. The repository, policy, standards and documentation advisors are the most developed.
- **It does not deposit for you.** The package is ready for you to upload yourself; automated deposit and minting DOIs are future work.
- Data management plan creation is deliberately out of scope for now.

## How you can help

- **Try it** and tell us where it confuses you: the [User Guide](https://data-director-agent.github.io/data-director/user-guide/) explains how. You do not need an API key to explore.
- **Data stewards:** we would value your view on the advice the advisors give, the questions they ask, and what a "deposit-ready" package should contain for your repository.
- **No code needed:** the guide has a *Giving feedback* page, and the repository offers issue forms for reviewing advice or specifications.

Code and documentation: <https://github.com/data-director-agent/data-director>

Thank you for your continued interest and input.
