# Setting up

```bash
uv sync --all-packages --all-extras
uv run pytest        # network blocked; everything runs offline
uv run ruff check .
uv run ruff format --check .
```

Every pull request must be signed off under the Developer Certificate of Origin: a
`Signed-off-by: Name <email>` line at the end of its description.
See `CONTRIBUTING.md` for the full process.

The workbench, the development way in to the harness, starts with:

```bash
uv run workbench serve   # then open http://127.0.0.1:8000/viewer/
```
