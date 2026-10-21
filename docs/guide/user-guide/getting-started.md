# Getting started

## Requirements

- [uv](https://docs.astral.sh/uv/) and Python 3.14 or later.
- A clone of the [repository](https://github.com/data-director-agent/data-director).

## Start the app

```bash
uv sync --all-packages
uv run data-director
```

Then open <http://127.0.0.1:7860>.

!!! tip
    `app/README.md` in the repository describes the app's configuration, which is in
    `app/config/`.
