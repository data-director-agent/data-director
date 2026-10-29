#!/usr/bin/env bash
# Decide which side of the repository a pull request touches, for the "changes" job in
# .github/workflows/ci.yml. Reads changed paths, one per line, on stdin and prints
# `python=true|false`, `web=true|false` and `deploy=true|false`, the job's outputs. The rules err towards running a
# job: the first matching pattern decides a path, and any path no rule names is the Python
# workspace's.
#
#   git diff --name-only main... | bash scripts/ci_changes.sh
set -euo pipefail

python=false
web=false
deploy=false
while IFS= read -r f; do
  case "$f" in
    "") ;;
    .github/dependabot.yml) ;;
    # The workflows and the Python toolchain decide every job.
    .github/* | pyproject.toml | uv.lock | .python-version) python=true web=true deploy=true ;;
    # The NGINX site is checked on its own; the rest of deploy/ is still the Python workspace's.
    deploy/nginx/* | deploy/install.sh | scripts/check_nginx.sh) python=true deploy=true ;;
    # app/tests writes app/web/fixtures and checks that they are current.
    app/web/fixtures/*) python=true web=true ;;
    app/web/*) web=true ;;
    app/*) python=true web=true ;;
    # CONFORMANCE.md is checked by the test job, and the packages' readmes by twine.
    CONFORMANCE.md | sdk/README.md | harness/README.md | workbench/README.md) python=true ;;
    # An agent's system prompt is Markdown but is the agent's code, which its tests check.
    agents/*/system_prompt.md) python=true ;;
    # Prose and the documentation site (docs.yml builds it; the docs job checks the links).
    *.md | docs/guide/* | docs/hooks.py | mkdocs.yml | LICENSE | CITATION.cff) ;;
    *) python=true ;;
  esac
  echo "$f: python=$python web=$web deploy=$deploy" >&2
done

echo "python=$python"
echo "web=$web"
echo "deploy=$deploy"
