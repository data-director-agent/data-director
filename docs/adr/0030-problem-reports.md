# ADR-0030: The app files problem reports as GitHub issues with a token it holds

**Status:** Accepted
**Date:** 2026-10-23

## Context

ADR-0024 quotes the Blueprint's "feedback mechanism" for the chat interface, and
`docs/ui/best-practices.md` asks for feedback capture with the person's consent. Nothing yet
lets a person tell the project that something is wrong or missing, and a report is of little use
without the build it was made on. The app did not say which version was running.

## Decision

- **The app files the issue.** `POST /api/feedback` takes a kind (`bug`, `feature` or `other`),
  a title and a description, and creates a GitHub issue in `DD_FEEDBACK_REPO`, with the issue
  type Bug, Feature or Task (the label `area: app` is always set). The person needs no GitHub
  account. Where GitHub refuses an issue type for the repository, the issue is filed without it
  and the body names the kind (#190).
- **The token is the app's, and it is narrow.** A fine-grained token for the one repository with
  Issues: write, read from `DD_FEEDBACK_GITHUB_TOKEN` or the credential file named by
  `DD_FEEDBACK_GITHUB_TOKEN_FILE`, as ADR-0026 does for a model key. ADR-0026 keeps model keys
  out of the app; this token can do nothing a model key can. Without it the feature is off: the
  page says so and links to GitHub, and the app still starts.
- **Every report names the build.** `GET /api/about` gives the app version, the harness version
  and the commit. The commit comes from `DD_REVISION`, else a `REVISION` file at the root of the
  release (`deploy/deploy.sh` writes it, as a release has no `.git`), else `git` in a checkout.
  The server adds all three to the issue itself; the page shows them but is not trusted for them.
- **Consent, and nothing sensitive.** The issue is public, and the page says so and shows what
  will be sent beside the form. The run and conversation the person came from are attached only
  if they tick a box, and then only as identifiers, agents, versions and outcomes read from the
  run store, never an input, a payload or evidence. The page's address is attached as a path.
- **Bounded.** A title may be 120 characters and a description 5000, unknown fields are refused,
  and the app files at most five reports in ten minutes for the whole process.
  TODO: settle these numbers on use, and count per person once people sign in (ADR-0029) (#188).

## Dependencies introduced

`httpx`, already a dependency of the harness, is now declared by the app.

## Consequences

- Anyone who can reach the app can file a public issue as the project's bot, as anyone behind the
  deployment's password can already run agents. Authentication (ADR-0029) will let a report name
  who made it; until then it does not.
- The token is a secret the app holds. Rotate it as any other, and give it no scope beyond
  Issues on this repository.
- A report made while the app is down, or from a deployment without a token, goes to GitHub by
  hand. The page links to the repository's issue form for that.
