# Pre-registration - Q121's remedy: quote restarted on the v2 world, then Q122's graph captured

**Written before quote is restarted. Nothing here is a result.** The owner chose on 2026-10-01 to
land Q121's remedy before Q122's snapshot of record is taken (`docs/design/t7.2-topology.md`,
"what the decision costs", item 1).

**The two questions.**

1. Does restarting quote bring its spans back to the time of the shipping call that makes them?
   This is the second of Q121's two predictions; the first, that the offset grows with each Mac
   sleep, held once on 2026-10-01.
2. With quote's clock right, does an hour of fresh traffic give the same cross-service edges as
   the 168 h capture taken through the skew?

## Read before registration

- **The offset.** quote's spans sat **1 day 12h06m10s** before the rest of their trace at
  2026-10-01 07:36 UTC (`docs/evidence/t7.2-topology/skew-probe-2.txt`). That was 17h29m03s more
  than at 2026-09-30 08:21, with the Mac asleep overnight between.
- **quote's container** started 2026-09-28 22:20:23 UTC and has not been restarted since, as the
  skew probe's container listing showed. No reboot of the Docker VM since then is known.
- **The 168 h capture**: 22 cross-service edges over 17 services, the same set as at 72 h
  (`docs/evidence/t7.2-topology/v2-dependencies-168h.json`).
- **The mechanism stays a hypothesis.** The PHP SDK takes a wall-clock reference once and adds
  monotonic time; the Docker VM's monotonic clock stops while the Mac sleeps. A restart retakes
  the reference. This run tests that prediction and does not establish the mechanism.

## What changes, and how it is undone

| change | undone by |
|---|---|
| `docker restart quote` on the Mac's v2 world, once | nothing to undo: the container keeps its image, configuration and name, and only its process restarts. A failed restart is handled by the stop rule |

**Nothing else changes**: no other container, no configuration, no file in the repository. Every
measurement below is read-only.

## The procedure, on the Mac

Every step's output is saved to `~/Downloads/q121-*.txt` and read before the next.

1. **The world check**: `python3 ~/Downloads/world_check.py`. The restart is gated on `ALL PASS`
   in the same command line, as the standing rule for world changes requires.
2. **Before**: `quote_offset.py before`, committed with this registration
   (`docs/evidence/t7.2-topology/quote_offset.py.txt`). It pairs each quote server span from the
   last ten minutes with shipping's client span above it and prints the offset.
3. **The restart**: `docker restart quote`, timed, with quote's start time and restart count read
   before and after.
4. **After**: two minutes later, `quote_offset.py after`.
5. **Kept awake**: from the restart to the end of step 7, the Mac is held awake with `caffeinate`.
   A sleep in that span voids step 7's capture, which is then repeated.
6. **At +60 minutes**: `quote_offset.py hour`, to confirm no skew came back.
7. **The capture**: `capture_v2_graph.py`, the same script as the 168 h capture, with lookbacks
   of 1 h, 24 h, 72 h and 168 h.

**The stop rule.** Stop and read before anything else if:

- quote is not `running` within 60 seconds of the restart;
- or its spans have not resumed in step 4's read (no quote span paired);
- or step 1 is not `ALL PASS`.

In any of those cases, nothing further is done until the owner decides.

## The outcomes, stated now

| question | answered yes when | answered no when |
|---|---|---|
| 1. the restart resets the offset | in step 4, **every** paired offset lies between 0 and +50 ms (quote starts just after shipping's call), against step 2's offsets of about −36 h | any offset in step 4 is more than 1 s from zero |
| 1b. it stays reset while the Mac is awake | step 6's offsets are likewise all between 0 and +50 ms | any offset in step 6 is more than 1 s from zero |
| 2. an hour of fresh traffic gives the 168 h graph | step 7's **1 h** reply has the same 22 cross-service edges as the committed 168 h reply, self-edges aside | the sets differ; the difference is named edge by edge |

**The snapshot of record**, fixed now. If question 2 is yes, it is **step 7's 1 h reply**: one
hour of traffic, every span dated right. If no, it is **the committed 168 h reply**, with the
difference written into Q122's build registration. Either way, Q122's build takes it from here.

**Predictions, stated now:**

- **Step 2** reads about **−36h06m**, or more if the Mac has slept since 07:36.
- **Step 4** reads **+0.1 to +5 ms** for every pair: shipping's call is a local HTTP request to
  quote.
- **Step 6** reads the same.
- **Question 2: yes.** The 1 h window read at 07:33 held every storefront and flag edge,
  including the rarest four flag reads at 5 calls each. What it lacked was the order path, which
  the skew had moved out of the window. With the skew gone, an hour of orders brings it back.

**Q121 itself stays open whatever the result.** A restart is a remedy only until the next sleep.
The durable guard (the world check failing when quote's offset exceeds a second) is Q121's other
remedy, and it is decided separately.

## What is recorded

- **The outputs.** `docs/evidence/t7.2-topology/q121-*.txt` and the new captures, verbatim.
- **Q121's row** carries the result of question 1.
- **Q122's row** names the snapshot of record, and Q122's build registration takes it from there.

## Addendum 1, 2026-10-01 - the gate held; load-generator is restarted first

**Step 1 stopped the run at 07:53:05 UTC, before anything changed.** 9 of 10 checks passed. The
failure was `no container but grafana >= 85 % memory`, with **load-generator at 87.9 %** of its
limit (`docs/evidence/t7.2-topology/q121-worldcheck-1.txt`). load-generator has run since
2026-09-28, and a Locust process's memory creeps over days. If it is OOM-killed during the
measured hour, the traffic behind question 2's capture has a gap.

**By the stop rule the owner decided: restart load-generator too.** The procedure gains a step 0,
and nothing else changes:

0. **`docker restart load-generator`**, with its start time, restart count and memory read before
   and after. Then **five minutes** for its users to ramp, and then step 1 as registered: the world
   check, with the quote restart gated on `ALL PASS` in the same run.

| change | undone by |
|---|---|
| `docker restart load-generator` on the Mac's v2 world, once | nothing to undo: same image, configuration and name, with a fresh process. A world check that still fails stops the run |

**What this moves.**

- **Question 1** (does quote's offset reset) does not depend on the load generator.
- **Question 2's hour** begins after both restarts, so it holds only fresh traffic either way.
- **What is lost** is the load generator's three-day history, which nothing here measures.
- **Prediction, added**: load-generator reads well under 85 % after its restart (a fresh Locust
  process, under 40 %), and the world check is `ALL PASS`.

**If the world check still fails** after step 0, the run stops again and nothing further is done
until the owner decides. The script gains step 0 and keeps every other step as run.
