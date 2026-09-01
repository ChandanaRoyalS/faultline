#!/usr/bin/env bash
# Refuse a commit made while on main (T7.47).
#
# Branch-before-commit was a rule this project followed by memory, and it failed once: T7.46
# committed to main and was caught only because the push had no branch to match. Every commit
# on main here arrives by squash-merge from a PR - 40 of the last 40 carry a `(#NN)` suffix -
# so a local commit on main is always the mistake, never the intent.
#
# Squash-merges happen on GitHub's side and never run this hook.
set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" != "main" ] || {
  echo "refusing: you are on main."
  echo "  Branch first:  git checkout -b <task-branch>"
  echo "  Every commit on main here arrives by squash-merge from a PR, so a local"
  echo "  commit on main is the mistake this hook exists to catch (T7.47)."
  echo "  If you genuinely mean it:  git commit --no-verify"
  exit 1
}
