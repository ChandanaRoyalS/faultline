# RESULT - Q121's remedy: quote restarted on the v2 world, then Q122's graph captured

Read against [`PREREGISTRATION-Q121-quote-restart.md`](../../runs/PREREGISTRATION-Q121-quote-restart.md)
and its Addendum 1. Run on 2026-10-01, 07:59:49-09:05:01 UTC, by the owner on the Mac, under
`caffeinate`, as one script (`q121_run.sh`, kept with the captures). Captures are verbatim in
[`docs/evidence/t7.2-topology/`](../../../docs/evidence/t7.2-topology/) (`q121-*`). $0, no model
call.

## The answers

**Question 1, as registered: NO on step 4. The read's window caused that, not quote, and the
substance is yes.** Step 4's read (08:06:58) searched the last ten minutes. That reached eight
minutes before the restart (08:04:58), so **26 of its 40 pairs came from traces made before the
restart** and read −1 day 12:06:11. Under the registered rule (*"any offset in step 4 more than 1
s from zero"*) that is **no**.

**The registration's read was the wrong instrument, and I wrote it.** It should have searched only
after the restart. The 14 pairs from after the restart read **−0.348 ms to +24.235 ms**. Three of
them are slightly below zero (−0.045, −0.208, −0.348 ms), so even those 14 sit just outside the
registered "0 to +50 ms". They are nowhere near the 1 s that defines "no".

**Question 1b: YES.** An hour after the restart (step 6, 09:05:00), **all 40 pairs** read **+27.3
to +29.2 ms**. Every one is inside 0 to +50 ms.

**So Q121's second prediction held in substance.** A restart brings quote's spans back from about
36 hours early to tens of milliseconds, and they stay there for an hour with the Mac awake. Its
first prediction (the offset grows with each sleep) held on 2026-10-01. **The mechanism is still a
hypothesis**, now consistent with both predictions.

**Question 2: YES.** An hour of fresh traffic gives the same graph. Step 7's **1 h** reply has
**exactly the 22 cross-service edges** of the committed 168 h capture, self-edges aside. So do the
24 h, 72 h and 168 h replies of the same run: every window agrees once the clock is right. **By the
registered rule, the snapshot of record for Q122 is step 7's 1 h reply**,
`docs/evidence/t7.2-topology/q121-v2-dependencies-1h.json` (endTs 1790845500936, 2026-10-01
09:05:00 UTC).

## The predictions

| prediction | held? |
|---|---|
| step 2 reads about −36h06m | **held**: −1 day 12:06:11 on all 40 pairs, one second more than at 07:36, with the Mac awake between |
| step 4 reads +0.1 to +5 ms on every pair | **wrong**: 26 pairs from before the restart (the window), and the 14 after it span −0.35 to +24.2 ms |
| step 6 reads the same | **wrong as to range**: +27.3 to +29.2 ms, not 0.1 to 5. The offset is small and stable, but it is not the near-zero the prediction gave |
| question 2: yes | **held** |
| Addendum 1: load-generator well under 85 % after its restart, under 40 % | **half held**: 44.4 % five minutes after (88.2 % before). Under 85, not under 40 |
| Addendum 1: the world check passes | **held**: ALL PASS at 08:04:55, load-generator's memory row now `none` |

**One thing the predictions did not foresee: +28 ms an hour later.** The 14 pairs just after the
restart clustered near zero: 10 of them within ±2.2 ms, and four at +14 to +24 ms. An hour
later, all 40 sat at +27 to +29 ms.
That is either quote's handling growing slower or quote's clock drifting about 28 ms in an hour.
**This run cannot tell which.** If it is drift, a clock that is right at restart is a few hundred
milliseconds off within a day of an awake Mac, and Q121's proposed gate (*"quote's server span
within a second of shipping's call"*) would catch it within days.

## Step by step

- **Step 0** (07:59:49). load-generator was at 4.308 GiB of 4.883 (88.24 %), up since
  2026-09-29T05:15:32. The restart took 3.4 s. Five minutes later it held 2.169 GiB (44.42 %).
- **Step 1** (08:04:55). The world check passed, 10 of 10. Cart's store spans read 2.43 a second
  against the defined "about 2".
- **Step 2** (08:04:57). All 40 pairs at −1 day 12:06:11. This computer and the Docker VM agreed
  to the second.
- **Step 3** (08:04:58). quote, up since 2026-09-28T22:20:23, restarted in 0.23 s, with
  `restarts 0` before and after (a manual restart is not counted).
- **Step 4** (08:06:58), as above.
- **Step 5.** `caffeinate` held from 07:59:49 to 09:05:01. Nothing shows a sleep: step 6's offsets
  would have jumped by the sleep's length.
- **Step 6** (09:05:00), as above.
- **Step 7** (09:05:00). The capture: 38 edges and 17 nodes in every window, all four replies
  kept.

## What follows

- **Q121 stays open.** The restart is a remedy until the next sleep, and the +28 ms is unexplained.
  The durable guard (the world check failing when quote's offset passes a second) is decided
  separately, and the +28 ms belongs to its measurement.
- **Q122's build** takes `q121-v2-dependencies-1h.json` as the v2 snapshot of record, and is
  registered next.
