#!/usr/bin/env bash
# Write the Markdown summary of a finished mutmut run: the counts, then each surviving mutant with
# its diff, then the functions no selected test reaches. Run from the member directory that holds
# `mutants/` (sdk/ or harness/), after `mutmut run`. Used by .github/workflows/mutation.yml.
#
#   bash ../scripts/mutation_summary.sh "Evidence hashing" >> "$GITHUB_STEP_SUMMARY"
set -euo pipefail

title=${1:?usage: mutation_summary.sh TITLE}

mutmut export-cicd-stats > /dev/null
results=$(mutmut results --all true)
# mutmut names a mutant `module.x_function__mutmut_N` or `module.xǁClassǁmethod__mutmut_N`.
function_of() { sed 's/__mutmut_[0-9]*$//; s/\.x_/./; s/\.xǁ\([^ǁ]*\)ǁ/.\1./'; }
names_with() { awk -v s="$1" -F': ' '$2 == s { gsub(/^ +/, "", $1); print $1 }' <<< "$results"; }

echo "## $title"
echo
jq -r '"| Killed | Survived | No tests | Timeout | Suspicious | Total |",
       "|---:|---:|---:|---:|---:|---:|",
       "| \(.killed) | \(.survived) | \(.no_tests) | \(.timeout) | \(.suspicious) | \(.total) |"' \
  mutants/mutmut-cicd-stats.json
echo

survived=$(names_with survived)
echo "### Surviving mutants"
echo
if [ -z "$survived" ]; then
  echo "None: every mutant that a test reaches made a test fail."
else
  echo "Each of these changes the code and no test fails. Add or tighten a test so that it does."
  echo
  echo "| Function | Surviving |"
  echo "|---|---:|"
  function_of <<< "$survived" | sort | uniq -c | sort -rn |
    while read -r count name; do echo "| \`$name\` | $count |"; done
  echo
  while read -r name; do
    echo "<details><summary><code>$name</code></summary>"
    echo
    echo '```diff'
    mutmut show "$name" | tail -n +2
    echo '```'
    echo
    echo "</details>"
  done <<< "$survived"
fi
echo

# A function with no tests is reached by none of the selected tests: the mutants in it can be
# neither killed nor survive, so they are listed by function rather than one by one.
untested=$(names_with "no tests" | function_of | sort | uniq -c)
if [ -n "$untested" ]; then
  echo "### Functions no selected test reaches"
  echo
  echo "| Function | Mutants |"
  echo "|---|---:|"
  while read -r count name; do
    echo "| \`$name\` | $count |"
  done <<< "$untested"
  echo
fi
