#!/usr/bin/env bash
# Start every agent service on the port app/config/agents.yaml names, for local development.
# Ctrl-C stops them all. Then, in another terminal: `uv run workbench serve` (or `invoke`).
# The work is done by `scripts/dev.py start --agents-only`, which also starts the app and the
# shell's dev server when run without that option.
set -euo pipefail

cd "$(dirname "$0")/.."
exec uv run scripts/dev.py start --agents-only
