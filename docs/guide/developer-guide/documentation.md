# Documentation

These pages are [MkDocs](https://www.mkdocs.org/) with the
[Material](https://squidfunk.github.io/mkdocs-material/) theme. The configuration, including the
navigation, is `mkdocs.yml`.

```bash
uv run --only-group docs mkdocs serve          # preview at http://127.0.0.1:8000
uv run --only-group docs mkdocs build --strict # as CI does; fails on broken links
```

The guides are in `docs/guide/`. Every other document stays where it is kept, next to what it
describes, and `docs/hooks.py` publishes it from there without a copy:

- In the `nav` of `mkdocs.yml`, a path that starts with `/` is a file from the repository root,
  such as `/harness/README.md`. A glob, such as `/docs/adr/*.md`, takes every match that the
  nav does not name elsewhere, so a new decision record appears without a change to the nav.
- Write links as they work on GitHub, relative to the file. A link to another published
  document goes to its page; a link to anything else, such as `docs/requirements.yaml`, goes to
  the file on GitHub.
- A Markdown file that git tracks and that is neither in the nav nor listed in `UNPUBLISHED` in
  `docs/hooks.py` fails the build, as does a link to a file that does not exist.

The `Docs` workflow builds the site on every pull request and publishes it to GitHub Pages when
`main` changes. In the repository settings, set Pages to the "GitHub Actions" source once.
