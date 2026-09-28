# Q100 — the narrative review the capability move required

**Date:** 2026-09-28 · **Task:** T7.1 (Q100) · **Reviewer:** Chandana Sorakundla

`CAPABILITY_VERSION` moved from `cap:d2b243e0` to `cap:91279a09`. As designed, that failed
`test_every_narrative_was_reviewed_against_the_current_capability_set` on all fifty bundles.
This document is the review the re-stamp rests on, in the shape
`docs/design/q94-capability-review.md` set. The prompt stamp moved with it, `8dda4a19da2f` to
`9ce16b66bbcc`, because the same change put a field on `Dispatch` and a paragraph in the
planner's prompt; that half is recorded in `tests/test_harness_run.py` (`Q100_DIGEST`) and is
not a narrative question.

## What moved, and what it could falsify

One capability input moved: `TOOL_BEHAVIOUR_REVISION` **4 → 5**. The tool surface is unchanged:
`logql_query` keeps its name and gains a parameter, `contains`, which `capability_version` does
not see - it reads names - and which is why the revision is hand-kept. `CAPTURE_SET` is
unchanged. One behaviour change sits behind the bump.

**A line filter.** `contains` goes to Loki as `|= "<text>"` after the stream selector, as a
string literal and nothing else (`logql_string` escapes it; `tests/test_tools.py` holds a hostile
filter to one literal). The two-ended cap then applies to the lines that match. The planner
reaches it through `Dispatch.log_filter`, on a logs dispatch only. **An unfiltered query returns
byte for byte what revision 4 returned** - no `|=`, no attribute - and a test says so.

*The claim shape this could falsify:* a narrative asserting that a line a responder needed was
out of the tool's reach - in the elided middle of a window, under a flood, reachable only by
narrowing a window the planner cannot narrow (Q17) - or advising a narrowed window as the only
way to it.

*What it cannot falsify:* any statement about what a log held. A filter selects from the stream;
it does not add to it. A narrative saying a service wrote nothing, or wrote only one line, or
wrote its startup banner and then stopped, is a claim about the world and stands.

## What the review looked for, and what it found

Every `incident.md` under `evals/scenarios/artifacts/dev/` (38, the two `INVALID` bundles
included since they carry a stamp) and `holdout/` (12) was searched for `elided`, `two ends`,
`the tool does not return`, `narrow`, `the log tool`, `whole incident`, `buried`, `drowned`,
`flooded`, `only healthy`, `could not find`, `could not read`, `not reachable`, and every hit
was read in context rather than counted.

| Claim shape | Hits | Disposition |
|---|---|---|
| A needed line out of the tool's reach, narrowing advised as the way to it | **2** | `v2-accounting-bad-credential`: *"the label and the exception's name were in the middle the tool does not return … Narrow the window to the start before concluding that a service's log is clean."* `v2-accounting-kafka-misconfig`: *"The `Connection refused` behind it is a few lines a minute under the flood, and the first is at the start: narrow the window there."* **Both true as written and both now incomplete**: the filter is a second way to those lines, and for the planner the only way. Each detection note gains one sentence naming the filtered read on the text the ends gave - `28P01`, `PostgresException`; `Connection refused`. The passages describing what the two ends held are unchanged, because that is what an unfiltered read still holds. Neither `expected_evidence` moves: both YAMLs describe the log's contents, not the tool's reach |
| "Narrowed to the start" as a description of what was done | **2, the same two** | `v2-accounting-bad-credential`'s *"Narrowed to the minutes after the start, the log was unambiguous"* and `v2-accounting-kafka-misconfig`'s *"Its logs, narrowed to the start"* describe a read that was made and what it showed. A read is not falsified by a second way of making it |
| "Whole incident", "narrow" elsewhere | **28** | Alert counts over the whole incident (12), error ratios and runtime series flat for the whole incident (8), a blast radius being narrow (3), a trace or a status narrowing the search (5). None is about the log tool |
| A stream that held nothing, or one line only | **many** | `v2-payment-telemetry-blackout`, `v2-cart-freeze`, `v2-currency-freeze`, the four partitions, the freeze row, the store-target rows: statements about what was written. A filter cannot change an empty stream or a stream of one line |

**Forty-eight narratives needed no change** and are re-stamped only. **Two gained one sentence
each** where the change left their advice incomplete: `v2-accounting-bad-credential` (dev) and
`v2-accounting-kafka-misconfig` (holdout). No narrative was falsified; no `expected_evidence`
moved; no scenario fingerprint moved.

## The conclusion, stated as a limit rather than as a pass

The stamps move to `cap:91279a09` on the basis above. **What this review did not do**, as at Q94
and T6.1: it did not re-verify each narrative's findings against its captures. It asked one
question derived from one change and answered it. A claim falsified by something else would not
have been caught here. The captures were not re-read for this move, and the message the guard
prints asks for that first; it is not done here because `CAPTURE_SET` did not move and the
tool's unfiltered output did not move, so nothing a capture holds reads differently than it did
at `cap:d2b243e0`.

**Three consequences outside the narratives.**

- `v2-accounting-bad-credential` is a v2 dev narrative, held out of the retrieval corpus until
  Q92 decides (`OTHER_WORLD_NARRATIVES`), so the corpus shape does not move here.
  `v2-accounting-kafka-misconfig` is holdout and in no corpus.
- Every figure at `cap:d2b243e0` stays a figure at `cap:d2b243e0`. There are none on the v2
  world, and none at `prompts:8dda4a19da2f` anywhere (README's own headline), so the double move
  strands nothing; a move after T7.2's first v2 sweep would have.
- The first `disk_fill` narrative, which Q100's trigger named, is written against this stamp: its
  onset line (*No space left on device*, at +5 s under the restart banners) is reachable by a
  filtered read, and the narrative may say so without advising a window the planner cannot set.
