#!/usr/bin/env bash
# Decide which parts of the repository a pull request touches, for the "changes" jobs in
# .github/workflows/ci.yml, accessibility.yml and codeql.yml. Reads changed paths, one per line, on
# stdin and prints the jobs' outputs:
#
#   python=true|false   the Python workspace (ci.yml; the viewer in accessibility.yml)
#   web=true|false      app/web and the libraries it links, inventory/browser and sdk/browser (ci.yml)
#   inventory=true|false  the command and its browser bundle, checked against each other (ci.yml)
#   deploy=true|false   the NGINX site and the systemd units (ci.yml)
#   gateway=true|false  the LiteLLM gateway's test stack, the model broker that calls it, and the
#                       backup of its database (ci.yml)
#   docs=true|false     the documentation site (accessibility.yml, which builds it)
#   codeql=[...]        the languages CodeQL analyses, as a JSON list (codeql.yml)
#
# The rules err towards running a job: the first matching pattern decides a path, and any path no
# rule names is the Python workspace's. With --all, every output is set, as for a push to main,
# the merge queue, the weekly run or a run started by hand.
#
#   git diff --name-only main... | bash scripts/ci_changes.sh
#
# With --release, for a pull request from release-please's branch, a change that only bumps
# versions (the changelogs, the manifest, `version` lines in pyproject.toml, uv.lock and the app's
# package files) sets every output to false: no code changed, and the merge queue runs every job on
# the result before it reaches main. The paths and the lines changed decide, not the branch name, so
# anything else on that branch falls through to the rules below. Run it where HEAD^1..HEAD is what
# the pull request changes (a pull request's merge commit).
set -euo pipefail

# Whether every line of `git diff` for a file, other than its header, changes only a version.
only_version_lines() {
  local pattern="$1" file="$2" line
  while IFS= read -r line; do
    [[ "$line" =~ $pattern ]] || return 1
  done < <(git -c core.quotepath=off diff -U0 --no-renames HEAD^1 HEAD -- "$file" | grep -E '^[+-]' | grep -vE '^(\+\+\+|---) ')
}

# Whether the paths in $1 (one per line) only bump versions.
is_version_bump() {
  local f any=false
  while IFS= read -r f; do
    case "$f" in
      "") continue ;;
      CHANGELOG.md | */CHANGELOG.md | .release-please-manifest.json) ;;
      pyproject.toml | */pyproject.toml | uv.lock)
        only_version_lines '^[+-]version = "[^"]*"$' "$f" || return 1 ;;
      app/web/package.json | app/web/package-lock.json)
        only_version_lines '^[+-] *"version": "[^"]*",?$' "$f" || return 1 ;;
      *) return 1 ;;
    esac
    any=true
  done <<< "$1"
  [ "$any" = true ]
}

if [ "${1:-}" = --release ]; then
  paths=$(cat)
  if is_version_bump "$paths"; then
    echo "release: only versions change" >&2
    for output in python web inventory deploy gateway docs; do echo "$output=false"; done
    echo "codeql=[]"
    exit 0
  fi
  exec bash "$0" <<< "$paths"
fi

if [ "${1:-}" = --all ]; then
  echo "python=true"
  echo "web=true"
  echo "inventory=true"
  echo "deploy=true"
  echo "gateway=true"
  echo "docs=true"
  echo 'codeql=["python","javascript-typescript","actions"]'
  exit 0
fi

python=false
web=false
inventory=false
deploy=false
gateway=false
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
    # The shell's API types are generated from the app's response models; the "mypy and
    # generated schemas" job checks that they are current.
    app/web/src/api/generated/*) python=true web=true ;;
    # The inventory library's readme is also on the documentation site.
    inventory/browser/README.md) web=true docs=true ;;
    # How to make an inventory, which the user guide renders too (docs/hooks_inventory.py).
    inventory/browser/src/making.json) web=true docs=true ;;
    # The agent view library's readme is also on the documentation site.
    sdk/browser/README.md) web=true docs=true ;;
    # Its card fixtures are written by sdk/tests/test_agent_view_fixtures.py.
    sdk/browser/tests/fixtures/*) python=true web=true ;;
    app/web/* | inventory/browser/* | sdk/browser/*) web=true ;;
    app/*) python=true web=true ;;
    # CONFORMANCE.md is checked by the test job, and the packages' readmes by twine; all of them
    # are on the site.
    CONFORMANCE.md | sdk/README.md | harness/README.md | workbench/README.md | inventory/README.md | admin/README.md)
      python=true docs=true ;;
    # An agent's prompts are Markdown but are the agent's code, which its tests check.
    agents/*_prompt.md) python=true ;;
    # The documentation site: docs/hooks.py publishes every other Markdown file, and
    # scripts/check_site_accessibility.py checks the site. The docs job in ci.yml checks links.
    *.md | docs/guide/* | docs/hooks.py | docs/hooks_inventory.py | mkdocs.yml | scripts/check_site_accessibility.py) docs=true ;;
    LICENSE | CITATION.cff) ;;
    *) python=true ;;
  esac
  # The browser bundle is the command run under Pyodide, so anything that changes the command, its
  # dependencies, the bundle's build, the browser scanner that runs it or the sample folder both
  # runtimes describe is checked again (inventory/browser/README.md). Independent of the rules above.
  case "$f" in
    .github/* | scripts/ci_changes.sh | uv.lock | inventory/src/* | inventory/pyproject.toml \
      | inventory/tests/data/mixed/* | inventory/browser/bundle/* | inventory/browser/package.json \
      | inventory/browser/package-lock.json | inventory/browser/src/scanner/* | inventory/browser/e2e/* \
      | inventory/browser/playwright.config.ts)
      inventory=true ;;
  esac
  # The gateway's test stack runs the gateway and the broker together, so a change to either, to
  # the SDK the broker is built on, or to the lock that pins both is checked against the other
  # (deploy/llm-gateway/README.md). Independent of the rules above.
  case "$f" in
    .github/* | scripts/ci_changes.sh | uv.lock | pyproject.toml | .python-version \
      | deploy/llm-gateway/* | broker/* | sdk/src/* | deploy/backup.sh | deploy/restore.sh \
      | deploy/stores.sh | deploy/gateway-store.sh | scripts/tests/test_backup.py)
      gateway=true ;;
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
  echo "$f: python=$python web=$web inventory=$inventory deploy=$deploy gateway=$gateway docs=$docs" >&2
done

languages=()
if [ "$codeql_python" = true ]; then languages+=('"python"'); fi
if [ "$codeql_js" = true ]; then languages+=('"javascript-typescript"'); fi
if [ "$codeql_actions" = true ]; then languages+=('"actions"'); fi

echo "python=$python"
echo "web=$web"
echo "inventory=$inventory"
echo "deploy=$deploy"
echo "gateway=$gateway"
echo "docs=$docs"
echo "codeql=[$(IFS=,; echo "${languages[*]+"${languages[*]}"}")]"
