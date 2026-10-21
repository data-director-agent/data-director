# Documentation

These pages are [MkDocs](https://www.mkdocs.org/) with the
[Material](https://squidfunk.github.io/mkdocs-material/) theme. The source is in `docs/guide/`
and the configuration, including the navigation, is `mkdocs.yml`.

```bash
uv run --only-group docs mkdocs serve          # preview at http://127.0.0.1:8000
uv run --only-group docs mkdocs build --strict # as CI does; fails on broken links
```

The `Docs` workflow builds the site on every pull request and publishes it to GitHub Pages when
`main` changes. In the repository settings, set Pages to the "GitHub Actions" source once.

The other documents in `docs/` (the Blueprint, decisions, register) are not part of the site's
source; the [reference](../reference/index.md) page links to them on GitHub.
