#!/usr/bin/env bash
# Decide which parts of the repository a pull request touches, for the "changes" jobs in
# .github/workflows/ci.yml, accessibility.yml and codeql.yml. Reads changed paths, one per line, on
# stdin and prints the jobs' outputs:
#
#   python=true|false   the Python workspace (ci.yml; the viewer in accessibility.yml)
#   web=true|false      app/web and the inventory library it links, inventory/browser (ci.yml)
#   deploy=true|false   the NGINX site and the systemd units (ci.yml)
#   docs=true|false     the documentation site (accessibility.yml, which builds it)
#   codeql=[...]        the languages CodeQL analyses, as a JSON list (codeql.yml)
#
# The rules err towards running a job: the first matching pattern decides a path, and any path no
# rule names is the Python workspace's. With --all, every output is set, as for a push to main,
# the merge queue, the weekly run or a run started by hand.
#
#   git diff --name-only main... | bash scripts/ci_changes.sh
set -euo pipefail

if [ "${1:-}" = --all ]; then
  echo "python=true"
  echo "web=true"
  echo "deploy=true"
  echo "docs=true"
  echo 'codeql=["python","javascript-typescript","actions"]'
  exit 0
fi

python=false
web=false
deploy=false
docs=false
codeql_python=false
codeql_js=false
codeql_actions=false
while IFS= read -r f; do
  case "$f" in
    "") ;;
    .github/dependabot.yml) ;;
    # The workflows, these rules and the Python toolchain decide every job.
    .github/* | scripts/ci_changes.sh | pyproject.toml | uv.lock | .python-version)
      python=true web=true deploy=true docs=true ;;
    # The NGINX site and the systemd units are checked on their own; the rest of deploy/ is still
    # the Python workspace's.
    deploy/nginx/* | deploy/systemd/* | deploy/systemd-lint-baseline.txt | deploy/install.sh | scripts/check_nginx.sh | scripts/check_systemd.sh)
      python=true deploy=true ;;
    # app/tests writes app/web/fixtures and checks that they are current.
    app/web/fixtures/*) python=true web=true ;;
    # The inventory library's readme is also on the documentation site.
    inventory/browser/README.md) web=true docs=true ;;
    # How to make an inventory, which the user guide renders too (docs/hooks_inventory.py).
    inventory/browser/src/making.json) web=true docs=true ;;
    app/web/* | inventory/browser/*) web=true ;;
    app/*) python=true web=true ;;
    # CONFORMANCE.md is checked by the test job, and the packages' readmes by twine; all of them
    # are on the site.
    CONFORMANCE.md | sdk/README.md | harness/README.md | workbench/README.md | inventory/README.md)
      python=true docs=true ;;
    # An agent's prompts are Markdown but are the agent's code, which its tests check.
    agents/*_prompt.md) python=true ;;
    # The documentation site: docs/hooks.py publishes every other Markdown file, and
    # scripts/check_site_accessibility.py checks the site. The docs job in ci.yml checks links.
    *.md | docs/guide/* | docs/hooks.py | docs/hooks_inventory.py | mkdocs.yml | scripts/check_site_accessibility.py) docs=true ;;
    LICENSE | CITATION.cff) ;;
    *) python=true ;;
  esac
  # CodeQL reads source by language, without building it.
  case "$f" in
    .github/workflows/codeql.yml | scripts/ci_changes.sh)
      codeql_python=true codeql_js=true codeql_actions=true ;;
    .github/workflows/* | .github/actions/* | */action.yml | */action.yaml) codeql_actions=true ;;
    *.py | *.pyi | pyproject.toml | */pyproject.toml | uv.lock) codeql_python=true ;;
    *.js | *.mjs | *.cjs | *.jsx | *.ts | *.mts | *.cts | *.tsx | *.html | *.vue \
      | package.json | */package.json | package-lock.json | */package-lock.json)
      codeql_js=true ;;
  esac
  echo "$f: python=$python web=$web deploy=$deploy docs=$docs" >&2
done

languages=()
if [ "$codeql_python" = true ]; then languages+=('"python"'); fi
if [ "$codeql_js" = true ]; then languages+=('"javascript-typescript"'); fi
if [ "$codeql_actions" = true ]; then languages+=('"actions"'); fi

echo "python=$python"
echo "web=$web"
echo "deploy=$deploy"
echo "docs=$docs"
echo "codeql=[$(IFS=,; echo "${languages[*]+"${languages[*]}"}")]"
