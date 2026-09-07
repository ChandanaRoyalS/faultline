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

**One line of this transcript is a defect, and it is kept.** `Class of fix: None` under THE VERDICT
is not what the verdict said — the artifact beside it (`…-verdict.json`) names `config_revert`
under `remediation_class`, the field's name in the `Verdict` contract. The narration read a key (`class_of_fix`) that no verdict ever
had, so every demo ever run printed `None` there, including the take in the video. Found by reading
this transcript during T5.6's audit, recorded as finding thirty-three in `docs/PLAN.md`, fixed in
`evalharness.demo` with the test that was missing; the transcript is a record of a run and is not
edited to match the fix.

A note on the file: `make demo` overwrites `transcript.txt` in place, so a local run replaces
this record. The committed copy carries an editorial header marking where the run's own output
begins; everything below that line is unedited.

The abstention is also worth watching on its own terms. The verdict names its own gap — *"the
evidence in hand cannot distinguish among these"* — and the narrative closes with five ranked
next steps, the first of which is the query it did not make. That is the behaviour this system
is built for: it is designed to say `unknown` rather than guess, and abstentions are reported as
coverage rather than folded into an accuracy figure.

## The video

[`faultline-demo-v0.1.mp4`](https://github.com/ChandanaRoyalS/faultline/releases/download/v0.1/faultline-demo-v0.1.mp4) — 4 min 25 s, attached to the `v0.1` release rather than committed,
because a 20 MB binary in a repository whose pre-commit hook refuses large files is the wrong shape.
The specification's beats (T5.3: *"inject, live investigation, cited report, remediation as
proposal, 10-scenario eval table"*), in four parts, each opened by a title card:

| part | what it shows | source |
|---|---|---|
| 1 | `make demo` on the development Mac, recorded from before the command was typed: the gate, the injection, then the 13-minute wait compressed 9.9×, then the recovery confirmation and the closing lines in real time | run `20260907T103142Z-cart-redis-misconfig` — **`bad_config` against `bad_config`, high confidence, \$0.7124** |
| 2 | the same incident on the incident screen: report, ranked alternatives, evidence cards, and `metric_baseline · frontend` clicked into Grafana Explore with the specialist's own PromQL | the Mac's own `make ui` |
| 3 | the live deployment — an incident it opened and investigated by itself, on the public URL | `https://faultline.chandanasorakundla.com/ui/incidents/6fb0c8c2…` (T5.5c) |
| 4 | README's Results table, with every figure carrying its n | GitHub |

**Three takes were recorded on 2026-09-07 and this is the third. The other two are in `evals/runs/`,
marked `demo`, and are not deleted.**

- `20260907T093422Z` **abstained** with the right service named; the screen recording had started
  three minutes late and missed the injection, the specification's first beat.
- `20260907T095840Z` was **wrong** — `dependency_latency` — with Jaeger answering HTTP 500 on the one
  trace query that would have named the callee. Reading Jaeger's log gave the reason: `json:
  unsupported value: NaN` — a span somewhere in the world carries a NaN-valued tag, Go's JSON encoder
  refuses it, and the whole search fails instead of the one span. That is one defect behind two Mac
  500s (T5.4b's rehearsal run and this one) and is recorded as **finding thirty-two** in
  `docs/PLAN.md`; the fix is digest-locked (`docs/QUEUE.md` Q26).
- `20260907T103142Z`, the take used, was recorded **after `docker restart jaeger`** — the same
  operational step TROUBLESHOOTING documents for Kafka, emptying an in-memory store that held the
  poisoned span. The planner did not need traces in the end; it reasoned that a pre-RPC connect
  refusal creates no server-side span and went to cart's logs and change history instead.

**What choosing the third take does and does not mean.** Demo runs are marked `demo` in their
manifest and never enter a sweep aggregate, so nothing in `docs/RESULTS.md` moved. The infrastructure
was fixed before the take, not the agent — no prompt, bound or tool changed, and the stamp is the
same `b6837dd449ca` every published figure carries. But the take *was* selected by its outcome from
three, and a reader should know that: on this scenario the current world's record is roughly two
correct in three, and the video shows one of the two.

**How it was cut.** Four QuickTime screen recordings (⌘⇧5), one `ffmpeg` invocation, no editor. The
script and the title-card images are kept beside this file in `docs/demo/video/` so the cut is
reproducible from the recordings; the recordings themselves are not committed.
