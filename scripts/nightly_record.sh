#!/usr/bin/env bash
# T4.5: where a night's runs land, so that "appended to the eval database" is true after the job.
#
# The nightly's Postgres is booted by `make eval-up` and torn down with the job, so a row loaded
# there is gone by morning. The durable eval database is `evals/runs/` in git: `faultline-eval-db
# load` rebuilds every table from the manifests there, which is how 537 runs were loaded on
# 2026-09-10. A night that leaves its run directories only in a 90-day build artifact has appended
# to nothing.
#
# So the night commits them - **never to main.** Main advances only by the owner's squash-merge
# (scripts/no-push-to-main.sh, tests/test_repo_guards.py), and a workflow is not the owner. The
# run directories go onto a long-lived results branch, on top of main, in one commit per night;
# the workflow then opens a pull request from that branch if none is open, and the owner
# squash-merges it when she reads it. README's table cannot move on that merge: a runner's run is
# generation `<digest>@Linux/x86_64` and the table filters on the generation (T5.4c, ADR-0030
# addendum), and `variance.TIERS["nightly"]` is R = 1, *"not a finding on its own"*.
#
# Authored as main's last commit is authored - the owner - because every commit in this
# repository is hers (CLAUDE.md), and a commit made on her schedule by her workflow is not an
# exception. The message says which run made it.
#
# Usage: scripts/nightly_record.sh [results-branch] [label]
#   results-branch  default nightly-results
#   label           default eval-nightly; the workflow passes its run id
#
# Exit 0 with "nothing to record" when no new run directory exists - a night that was refused at
# the key, or scored nothing, must not create an empty commit.
set -euo pipefail

branch="${1:-nightly-results}"
label="${2:-eval-nightly}"
remote="${NIGHTLY_REMOTE:-origin}"
base="${NIGHTLY_BASE:-main}"

root="$(git rev-parse --show-toplevel)"
cd "$root"

# Tonight's run directories: whatever is under evals/runs/ that git does not know about. A run
# directory is `evals/runs/<stamp>-<scenario>/`; INVALID.md and the sweep documents are tracked
# and are not touched here.
mapfile -t new_dirs < <(git ls-files --others --exclude-standard evals/runs | cut -d/ -f1-3 | sort -u)
if [ "${#new_dirs[@]}" -eq 0 ]; then
  echo "nothing to record: no new directory under evals/runs/"
  exit 0
fi

stash="$(mktemp -d)"
for d in "${new_dirs[@]}"; do
  mkdir -p "$stash/$(dirname "$d")"
  cp -R "$d" "$stash/$d"
done

# Only new directories travel. A tracked file the job touched - INVALID.md, a sweep document - is
# not the night's to change; put it back before switching branches so it neither blocks the
# checkout nor rides along.
git checkout -q -- evals/runs

author_name="$(git log -1 --format='%an' "$remote/$base")"
author_email="$(git log -1 --format='%ae' "$remote/$base")"

git fetch -q "$remote" "$base"
if git fetch -q "$remote" "$branch" 2>/dev/null; then
  git checkout -q -B "$branch" "$remote/$branch"
  # Stay on top of main so the pull request is only ever the nights not yet merged.
  git -c user.name="$author_name" -c user.email="$author_email" merge -q --no-edit "$remote/$base"
else
  git checkout -q -B "$branch" "$remote/$base"
fi

cp -R "$stash/evals/runs/." evals/runs/
git add -- "${new_dirs[@]}"
if git diff --cached --quiet; then
  echo "nothing to record: every new directory is already on $branch"
  exit 0
fi

git -c user.name="$author_name" -c user.email="$author_email" commit -q -F - <<EOF
$label: ${#new_dirs[@]} run director$([ "${#new_dirs[@]}" -eq 1 ] && echo y || echo ies) recorded

$(printf '  %s\n' "${new_dirs[@]}")

Tier nightly, R = 1: change detection, not a finding. Made on a GitHub-hosted runner, so
generation <digest>@Linux/x86_64 - never pooled with the reference platform, never in
README's table. Recorded by $label.
EOF

git push -q "$remote" "$branch"
echo "recorded ${#new_dirs[@]} run director$([ "${#new_dirs[@]}" -eq 1 ] && echo y || echo ies) on $remote/$branch"
