# The ten world runbooks, and the corpus reaching 50

**Date:** 2026-09-12. **Task:** T6.4. **Subject:** `world-alert-timing`,
`-blast-radius-traversal`, `-change-records-have-no-prior-value`, `-digests-and-what-they-cover`,
`-emulated-containers`, `-log-volume`, `-runtime-metrics-and-their-label`, `-the-settle-window`,
`-two-names-for-every-service`, `-what-a-recreate-removes`.

**The corpus is at 50 documents** — 40 runbooks and 10 narratives — which is the figure
`PREREGISTRATION-T6.4.md` registered. One review round, before the PR.

## A deviation from the registered list, stated rather than buried

The pre-registration gave example topics for the ten `world-*` documents, two of which have since
been written elsewhere: **kafka's translation-cache growth and why raising the limit is not the
remedy** is now the larger half of `service-kafka`, and **the feature-flag stub's standing** is
`world-uninstrumented-services`. Writing either again would duplicate a seeded document.

Substituted, and each is a property of this world or of one of its instruments in the same sense:
blast-radius traversal semantics, digest coverage, the naming schemes, the runtime-metric label,
log volume, and change records. The registered topics that *were* written as registered: the
settle window, alert timing versus scrape interval, and what a recreate does and does not remove.

## The defect this batch found in the last one

Compiling the fact sheet turned up something the Q35 repair had shipped and three review rounds
had passed: **`class-bad-deploy` and `class-bad-config` both said a change record holds the old
and the new value.** It holds the new value only —
`injector.changelog.describe` returns `None` in the `before` position in all six of its branches,
and the reverting record carries the faulted value with no `after`.

`ORIGINAL-FIFTEEN.md` now records it, because it is the most instructive of that batch's eleven
findings for three reasons: the correction was already in ADR-0032's addendum, landed the day
before; `class-bad-config`'s Q35 repair rewrote that sentence and carried the false half across;
and three review rounds passed it while listing it as verified clean.

**The reason generalises and is worth having on its own: the review checked new prose against the
ADRs it cited and never against the code it described.** A claim about what a function writes is
checkable only by reading the function. Two `action-*` documents had a related problem — both
stated allowlist preconditions as though the executor evaluates them, when ADR-0032's addendum
records those as unmeetable as written and reinterpreted as drift. Both now carry the catalog's
prose *and* the executable meaning.

`world-change-records-have-no-prior-value` is the document that should have existed before any of
this, and it exists now.

## What the review round found

One blocking finding and three minor, against seventy-odd checked claims. The blocking one is
worth recording for where it landed rather than for what it was: a sentence in
`world-digests-and-what-they-cover` that quoted a source correctly, dropped the antecedent, and
became unparseable.

**That is the document with no sibling to disagree with.** Nine of the ten restate or extend
something a service runbook, an alert runbook or an ADR already says, so a wrong claim collides
with something. Digest coverage is explained nowhere else in the corpus, and it is the one that
carried a broken sentence through a fact sheet, a transcription and a self-review untouched.

**If there is ever a third batch, the documents with no cross-check are the ones to read last and
slowest.** That is a process finding rather than an editorial one, and it came from the reviewer.

The three minor findings were a count inherited faithfully from a source whose own heading says
three and then names four; an inference about which of thirteen graph nodes is the one that needs
canonicalising, which the node list does not support; and a drift comparison stated one field
short.

## What this does not settle

- **Whether the fact sheet was right.** Same limit as the service batch, and this is the second
  sheet nobody reviewed directly. It did surface a real defect in already-merged material, which
  is evidence the process finds things — not evidence the sheet is complete.
- **Whether any of the fifty documents help.** That is the recall measurement, which is now the
  only thing T6.4 has left and has been deferred through four batches.
- **Whether 50 is a useful size.** It is the plan's number. A corpus of fifty short documents is
  small enough that a dense retriever has an easy time of it, and the figure should be read that
  way and re-read if the corpus ever reaches a few hundred.
