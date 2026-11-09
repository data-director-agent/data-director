# Setting up

```bash
uv sync --all-packages --all-extras
uv run pytest        # network blocked; everything runs offline
uv run ruff check .
uv run ruff format --check .
```

Every pull request is signed off under the Developer Certificate of Origin: by opening it from
your own GitHub account you certify the DCO for it, and you may also end its description with a
`Signed-off-by: Name <email>` line, which is recorded in the merged commit.
See `CONTRIBUTING.md` for the full process.

The workbench, the development way in to the harness, starts with:

```bash
uv run workbench serve   # then open http://127.0.0.1:8000/viewer/
```
