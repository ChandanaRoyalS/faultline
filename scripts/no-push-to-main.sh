#!/usr/bin/env bash
# Refuse a push made while on main (T7.47, extended after B2 landed unreviewed).
#
# `no-commit-on-main.sh` guards the `pre-commit` stage, and that turned out to guard one
# entrance out of several. `git am` runs `applypatch-msg`, `pre-applypatch` and
# `post-applypatch` - never `pre-commit` - so a patch applied while on main committed and
# pushed with no hook in its way. That is how B2 (7fae7b1) reached main with no PR, and every
# patch handed over in this project lands by `git am`, so the hole had been open for weeks and
# only opened onto main when a restarted shell left the working tree there between two steps.
#
# The fix guards the *push* rather than the commit, because the push is where a local mistake
# becomes a shared one, and because one check at that boundary covers every entrance:
# `git am`, `cherry-pick`, `merge`, `rebase`, and `commit --no-verify` alike. The pre-commit
# framework has no `pre-applypatch` stage, so a like-for-like hook was not available anyway.
#
# The claim this rests on is checkable, and stated at the width that survives the check. Of the
# last 40 commits on main, exactly one lacks a `(#NN)` squash-merge suffix - 7fae7b1, the
# mistake above. Earlier history has 24 more, all from before branch-and-PR was the rule, which
# is why the claim is about recent history rather than all of it:
#
#   git log --oneline -40 origin/main | grep -cv '(#[0-9]\+)$'   # 1, and it is 7fae7b1
#
# So nothing legitimate is pushed to main from a laptop, and this hook costs nothing to keep.
#
# Squash-merges happen on GitHub's side and never run this hook.
set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" != "main" ] || {
  echo "refusing: you are on main, so this push would write to main."
  echo
  echo "  Every commit on main here arrives by squash-merge from a PR. A push from"
  echo "  a laptop is the mistake this hook exists to catch - it is the one that let"
  echo "  B2 (7fae7b1) reach main with no review, because 'git am' runs no pre-commit"
  echo "  hook and there was nothing guarding the push."
  echo
  echo "  To land work you already committed on main:"
  echo "    git branch <task-branch>          # keep the commits"
  echo "    git reset --hard origin/main      # move main back"
  echo "    git checkout <task-branch> && git push -u origin <task-branch>"
  echo
  echo "  If you genuinely mean it:  git push --no-verify"
  exit 1
}
