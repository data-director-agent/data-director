# Contributing to data-director

Thank you for your interest in contributing to `data-director`, a reference implementation of the
Research Data Alliance's Data Director Agentic AI Blueprint. This project is community-driven and
welcomes issues, discussion, and pull requests.

## Before you start

- **Bugs and small changes**: open an issue or go straight to a pull request.
- **Changes affecting spec conformance** (interfaces, data models, or behaviour defined by the
  Blueprint): open an `RFC` issue first. See [GOVERNANCE.md](GOVERNANCE.md#rfc-process-for-spec-conformance-changes)
  for the process.

## Repository structure

This repository is organised as follow:

* `docs/` contains documentation
* `experiments/` contains prototype work

## Developer Certificate of Origin (DCO)

Every commit must be signed off to certify that you wrote it or otherwise have the right to submit
it under the project's license, per the [Developer Certificate of Origin](DCO.md).

Sign off each commit by adding the `-s` flag:

```sh
git commit -s -m "Your commit message"
```

This appends a `Signed-off-by` trailer with your name and email to the commit message, e.g.:

```
Signed-off-by: Jane Doe <jane@example.com>
```

Use your real name and a working email address — anonymous or pseudonymous sign-offs cannot be
accepted. Pull requests containing unsigned commits will be asked to amend before merge.

Your affiliation (declared via your sign-off name/email or stated in the PR description) also
helps the maintainers track the [Technical Steering Committee trigger](GOVERNANCE.md#technical-steering-committee-tsc).

## Pull request workflow

1. Fork the repository and create a branch for your change.
2. Make your change, with tests where applicable.
3. Ensure all commits are signed off (see above).
4. Open a pull request against `main` describing the change and its motivation. Link to the
   relevant issue or RFC if there is one.
5. A maintainer reviews and approves. Per [GOVERNANCE.md](GOVERNANCE.md#decision-making-lazy-consensus),
   the pull request merges under lazy consensus once approved and no objection is raised within
   the review window.

## Code style and testing

The project's tooling (language, linting, test framework) is still being established. Guidance on
code style and how to run tests will be added here once that tooling is in place — for now, follow
the conventions of the surrounding code and describe how you tested your change in the pull
request description.

## Getting help

Open an issue with your question, or start a discussion thread if the repository has discussions
enabled.

## Repository

`TODO: repository URL`
