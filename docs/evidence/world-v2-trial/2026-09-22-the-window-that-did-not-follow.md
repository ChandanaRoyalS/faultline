# The window that did not follow — 2026-09-22

**\$0, no model call, found by reading rather than by running.** The v2 alert rules widened from
`[2m]` to `[5m]`. **The capture queries did not.** They were hard-coded, in f-strings, in the two
places that build PromQL:

```
src/evalharness/prom.py         metric_queries()   [2m]  ×3
src/faultline/tools/metrics.py  render_query()     [2m]  ×3
```

T7.1 parameterised the span-metric **names** for v2 (patch 0102) and left the window behind. Nobody
noticed because a window is not a name and the tests that freeze those expressions froze them
*including* the window, correctly, as v1's.

## Why this was about to cost the re-baseline

A capture taken in that state writes two things into one `summary.md`:

- the `error-ratio`, `latency-p95` and `call-rate` tables, smoothed over **`[2m]`** — which on this
  world means six to eight samples per window, and therefore **the same 15000 ms p95s and error
  ratios to 100%** that the first baseline reported and diagnosed as sampling noise;
- the `alerts-firing` series, produced by rules evaluating **`[5m]`** — empty, if the widening did
  what it was meant to.

**The obvious reading of that summary is "the world is still too noisy, the widening did not
work."** It would have been wrong, and it is the third time in one day that a reading of this world
would have been an artefact of an instrument rather than a fact about the world. The first was the
`[2m]` noise itself; the second was the stale rule set
([the mount that detached](2026-09-22-the-mount-that-detached.md)); this is the third.

**It was found before the run rather than after, which is the only cheap version.** The trigger was
unrelated: checking whether committing the void capture would break anything led to reading
`metric_queries()`, which is where the `[2m]` is.

## The fix

**The window moved onto the per-world object**, which is renamed for it: `SpanMetricNames` →
`WorldMetrics`, with `calls`, `duration_bucket` and `rate_window`. `V1` carries `2m`, `V2` carries
`5m`, and `metrics_for(world)` returns one or the other.

**One object, so that the wrong pairing cannot be expressed.** The alternative — a second lookup
returning a window, passed beside the names — is what produced this defect in the first place: two
things that must agree, changeable independently. A caller can no longer hold v2's names with v1's
window, because there is nothing to hold them in.

**Not `WindowPolicy`, and that is worth stating** because the name invites it. `WindowPolicy` bounds
which *timestamps* a range query fetches — onset minus lookback, clipped at a ceiling. This is the
smoothing interval inside the expression. They are both called windows and they are not the same
quantity; folding one into the other would make both harder to reason about.

## What pins it

- **`test_the_v2_capture_window_is_the_window_the_v2_rules_evaluate`** reads the detection window
  out of `compose/prometheus/alert-rules-v2.yml` and asserts it equals `V2.rate_window`. **This is
  the guard that matters**: the capture and the rules are two views of one instrument, and the
  defect was that nothing said so.
- **The v1 freeze is unchanged and still passes byte for byte.** `render_query` and
  `metric_queries()` produce exactly the strings 197 scored runs were measured through, which is
  the whole safety argument for touching them at all. Both stamps are unmoved:
  `prompt_digest 06f24e827915`, `capability_version cap:dd651ccc`.
- **`manifest.json` now records `rate_window`**, and `summary.md` states it in the Queries heading.
  A capture that cannot say which window produced its numbers is a capture whose numbers cannot be
  compared with another's.

## What this exposed and did not fix: Q86

**`capability_version` does not distinguish the world a run was taken in.** It hashes
`tool_surface()`, `CAPTURE_SET` and `TOOL_BEHAVIOUR_REVISION`, and none of those move when
`FAULTLINE_TOOLS_WORLD` changes — so a v1 run and a v2 run of the same tool layer carry **the same
capability stamp**, while `metric_query` returns a differently-named series over a different window.

**Not fixed here, deliberately.** Nothing is currently mis-stamped, because no v2 run has been
recorded. The obvious fix — bumping `TOOL_BEHAVIOUR_REVISION` — would move the stamp for all 197
scored v1 runs, whose tool behaviour is frozen byte for byte and demonstrably did not change.
Spending the corpus's comparability on a change that does not affect it is the wrong trade.

**It becomes a live defect at the first recorded v2 run**, which is T7.1's re-record. Queued as
**Q86** with that trigger. `manifest.json` already carries `world` for baselines; runs carry
nothing, and that is the gap.

## v1 is left alone, and one v1 discrepancy is recorded rather than fixed

v1's rules are **not** uniform: `ServiceHighErrorRate` and `ServiceHighLatency` detect over `[2m]`
and **`ServiceNoTraffic` over `[3m]`**, while every v1 capture was smoothed over `[2m]`. The
same-window invariant this note establishes therefore holds on v2 and **does not hold on v1**, which
is why the guard is v2-only.

It is a small discrepancy — for a `== 0` rule the window width changes when it trips, not whether —
and **v1 is frozen**: every published figure was measured on that world, and changing its queries or
its rules to satisfy a property discovered afterwards would cost the corpus and buy nothing. Written
down here so the asymmetry is a decision rather than an oversight.
