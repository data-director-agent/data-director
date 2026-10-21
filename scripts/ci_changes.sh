#!/usr/bin/env bash
# Decide which side of the repository a pull request touches, for the "changes" job in
# .github/workflows/ci.yml. Reads changed paths, one per line, on stdin and prints
# `python=true|false` and `web=true|false`, the job's outputs. The rules err towards running a
# job: the first matching pattern decides a path, and any path no rule names is the Python
# workspace's.
#
#   git diff --name-only main... | bash scripts/ci_changes.sh
set -euo pipefail

python=false
web=false
while IFS= read -r f; do
  case "$f" in
    "") ;;
    .github/dependabot.yml) ;;
    # The workflows and the Python toolchain decide every job.
    .github/* | pyproject.toml | uv.lock | .python-version) python=true web=true ;;
    # app/tests writes app/web/fixtures and checks that they are current.
    app/web/fixtures/*) python=true web=true ;;
    app/web/*) web=true ;;
    app/*) python=true web=true ;;
    # CONFORMANCE.md is checked by the test job, and the packages' readmes by twine.
    CONFORMANCE.md | sdk/README.md | harness/README.md | workbench/README.md) python=true ;;
    # Prose and the documentation site (docs.yml builds it; the docs job checks the links).
    *.md | docs/guide/* | mkdocs.yml | LICENSE | CITATION.cff) ;;
    *) python=true ;;
  esac
  echo "$f: python=$python web=$web" >&2
done

echo "python=$python"
echo "web=$web"
