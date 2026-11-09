#!/usr/bin/env bash
# Make the person an agent session works for the author of its commits.
#
# CI (scripts/check_signoff.py) rejects a commit whose author is a coding agent, and one with no
# `Signed-off-by` naming its author. A cloud session commits as `Claude <noreply@anthropic.com>`,
# so every pull request it opens fails until someone rewrites the author. This script, run by the
# SessionStart hook in .claude/settings.json, sets only the *author* from the environment:
#
#     DD_AUTHOR_NAME   the person's name, as in their `Signed-off-by`
#     DD_AUTHOR_EMAIL  their email, byte for byte as in their `Signed-off-by`
#
# It exports GIT_AUTHOR_NAME and GIT_AUTHOR_EMAIL for the session's shell commands through
# CLAUDE_ENV_FILE and nothing else. The committer stays the agent, and it adds no sign-off: only
# the person signs off, after they have reviewed the work, with `git rebase --signoff BASE`
# (AGENTS.md). With either variable or CLAUDE_ENV_FILE unset it does nothing, so no identity is
# written into the repository.

set -euo pipefail

name="${DD_AUTHOR_NAME:-}"
email="${DD_AUTHOR_EMAIL:-}"
env_file="${CLAUDE_ENV_FILE:-}"

if [[ -z "$name" || -z "$email" || -z "$env_file" ]]; then
    exit 0
fi

# A newline would split the assignment, and `<` or `>` would corrupt the `Name <email>` identity.
if [[ "$name$email" == *$'\n'* || "$name$email" == *[\<\>]* ]]; then
    echo "agent_git_identity.sh: DD_AUTHOR_NAME and DD_AUTHOR_EMAIL must not contain a newline, '<' or '>'" >&2
    exit 1
fi

{
    printf 'export GIT_AUTHOR_NAME=%q\n' "$name"
    printf 'export GIT_AUTHOR_EMAIL=%q\n' "$email"
} >>"$env_file"
