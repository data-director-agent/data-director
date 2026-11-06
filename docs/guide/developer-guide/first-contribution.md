# Your first contribution

This page takes you from a fresh clone to an open pull request. You do not need to read the
governance documents first; the [contribution guide](../../../CONTRIBUTING.md) covers the rest
when you need it.

## What do you want to do?

| I want to… | Do this |
|---|---|
| Fix a typo or improve a document | Edit the file on GitHub (the **Edit this page** link on every page of this site does it) and open a pull request. No setup is needed. |
| Report a bug | [Open a bug issue](https://github.com/data-director-agent/data-director/issues/new/choose) with the steps that reproduce it. |
| Review the Blueprint mapping, or the advice an agent gave | Use the **Conformance review**, **Blueprint reading** or **Feedback on advice** issue form. You need no code ([Contributing without writing code](../../../CONTRIBUTING.md#contributing-without-writing-code)). |
| Fix a bug or add a small feature | Follow the steps below. |
| Add an agent | Read [Writing an agent](writing-an-agent.md), then follow the steps below. |
| Change how the system is meant to work (an interface, data model or behaviour the Blueprint defines) | Open an `RFC` issue first ([RFC process](https://github.com/data-director-agent/.github/blob/main/GOVERNANCE.md#rfc-process-for-spec-conformance-changes)). |

Not sure which applies? Open an issue and ask; a maintainer will point you to the right one.

## Steps

You need [`uv`](https://docs.astral.sh/uv/getting-started/installation/), Node 22 or later and a
Bash shell (on Windows, use WSL). No account or API key is needed.

1. **Fork and clone** the [repository](https://github.com/data-director-agent/data-director), and
   create a branch for your change. Branch names are lower-case words joined by hyphens, such as
   `fix-history-tab`.
2. **Set up.** From the root of the clone:

    ```sh
    uv run scripts/dev.py setup     # asks a few questions, then installs everything
    uv run scripts/dev.py doctor    # says what is wrong with your setup, if anything
    ```

    `setup --yes` accepts every default without asking. See the
    [README](../../../README.md#quick-start) for what `setup` writes and how to run the app with
    `uv run scripts/dev.py start`.
3. **Make your change.** Follow the conventions of the surrounding code. A change to the design
   changes its [specification](../../../docs/specs/README.md) in the same pull request.
4. **Run the tests.**

    ```sh
    uv run pytest                                          # offline; needs no credentials
    uv run ruff check . && uv run ruff format --check .
    uv run mypy
    ```

    The [contribution guide](../../../CONTRIBUTING.md#code-style-and-testing) lists how to run
    each of the other checks that CI runs, such as the app shell's.
5. **Commit with a sign-off**, so that you certify you may submit the work
   (the [Developer Certificate of Origin](https://github.com/data-director-agent/.github/blob/main/DCO.md)):

    ```sh
    git commit -s -m "fix(app): show the history tab without a run"
    ```

6. **Open a pull request** against `main`. Its title is a
   [Conventional Commit](https://www.conventionalcommits.org/) (`type(scope): summary`, in lower
   case), which the project uses to make releases. Describe what you changed, why, and how you
   tested it, and link the issue if there is one. Say if an AI tool wrote a substantial part.
7. **Add yourself to the [citation file](../../../CITATION.cff)** in your first pull request, so
   that you are credited as an author ([Credit](../../../CONTRIBUTING.md#credit)).

A maintainer reviews your pull request, and CI reports its checks on the page. If a check fails,
the log says which; fix it and push another commit. If you wait more than a few days for a
reply, comment on the pull request to ask.
