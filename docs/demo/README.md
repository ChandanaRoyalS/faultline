# The demo, recorded

What `make demo` produced on 2026-08-27, kept verbatim for anyone who would rather read than
spend fifteen minutes and forty cents.

| | |
|---|---|
| run | `20260827T120348Z-cart-redis-misconfig` (in `evals/runs/`, marked `demo`) |
| scenario | `cart-redis-misconfig` (dev) |
| stamp | `faultline/0.0.1+prompts:53fafe9c12bc` |
| budget | `changes` 8, others 4, 120k tokens, 600s, 2 rounds — the T4.7 configuration |
| cost | **$0.3978** |
| outcome | **`unknown` — abstained.** Ground truth `bad_config`. |

The budget above is **byte-identical** to the one T4.10's five repeats ran under — same stamp,
same four bounds — which is what makes this run a legitimate seventh observation of that
configuration rather than a differently-configured one. An earlier attempt during T5.3 ran at the
**default `changes` bound of 4** and is *not* comparable; it is kept at
`evals/runs/20260827T112506Z-cart-redis-misconfig` as a record of the defect, and is not this
transcript.

- [`transcript.txt`](transcript.txt) — the whole narrated run, exactly as it printed
- [`narrative.md`](narrative.md) — the incident record the scribe wrote, on its own

## About this particular run

**It abstained, and it is kept anyway.** Six prior runs at this exact configuration all returned
`bad_config` correctly (`evals/runs/VARIANCE-2026-08-27.md`, n = 5, plus dev sweep 3's row), so
this transcript shows the less common outcome.

What happened is legible in the transcript. The agents localized correctly — every failing
`PlaceOrder` trace aborts at `checkoutservice`'s outbound `CartService/GetCart` call, which is
exactly right — and then the planner spent five of its dispatches on per-dependency metrics,
**exhausted the metrics bound at 4 of 4**, and never spent a change-history query on
`cartservice`. The answer was one dispatch away and the plan did not contain it. The incident
was the same shape as all twelve other runs of this scenario (9 services alerting, 12 predicted,
recall 0.78), so this is planner allocation, not a different world.

**What it demonstrates is a designed behaviour.** Saying `unknown` rather than guessing is the
point: an abstention is reported as coverage and kept out of the accuracy figure entirely, so the
system is never rewarded for a confident wrong answer. The open question the run puts on display —
why the planner sometimes spends its budget without reaching the one service that holds the answer
— is the next candidate experiment in [`docs/PLAN.md`](../PLAN.md), and this run is an observation
of it at the current stamp.

**It was not re-rolled.** Re-running until the transcript flatters the system would make this an
advertisement rather than a record, and the project's own rule is that no figure leaves the
repository without its n. The honest n here is one run, and the honest record is 6 of 7.

A note on the file: `make demo` overwrites `transcript.txt` in place, so a local run replaces
this record. The committed copy carries an editorial header marking where the run's own output
begins; everything below that line is unedited.

The abstention is also worth watching on its own terms. The verdict names its own gap — *"the
evidence in hand cannot distinguish among these"* — and the narrative closes with five ranked
next steps, the first of which is the query it did not make. That is the behaviour this system
is built for: it is designed to say `unknown` rather than guess, and abstentions are reported as
coverage rather than folded into an accuracy figure.
