# Rehearsal artifact bundle (T1.5 / ADR-0009)

Every rehearsed scenario leaves exactly one bundle:

```
evals/scenarios/artifacts/<split>/<scenario-id>/
├── manifest.json          machine-readable facts and provenance
├── incident.md            the narrative — hand-written, the only file that matters most
├── queries.md             the exact PromQL behind every metrics/ file
├── metrics/
│   ├── error-ratio.json   query_range over the incident window
│   ├── call-rate.json
│   ├── latency-p95.json
│   └── alerts-firing.json ALERTS series — when each alert fired and cleared
└── logs/
    └── <target>.txt       best-effort Loki pull for the injected service
```

The path is the quarantine (T1.6): `<split>` is the scenario's own split, and the guard
tests in `tests/test_contamination.py` fail the build if a bundle lands on the wrong side.

## Recording one

```
uv run python -m evalharness.rehearse <scenario-id>
```

The recorder injects the fault, waits for an alert, holds steady state for five minutes,
reverts, waits for the alert to clear, then captures the metric window and writes
everything above. It drives the injector through its CLI only — never its internals — so
that T4.1 can later reuse the same boundary.

It cannot write `incident.md`. That one is yours.

## incident.md is the corpus

This is the file T2.4b seeds the past-incident store from, and it is the file a retrieval
agent will surface months later when it sees a similar incident. Everything else in the
bundle is supporting evidence; this is the thing that gets read.

Three rules. The first two are the difference between a corpus that teaches and one that
cheats; the third is what stops the writing being thrown away.

**Write it from the responder's chair, not the author's.** You know the root cause because
you injected it. The person the corpus is simulating did not. If the narrative opens with
"the flag service was deployed with a broken image", you have written an answer key, and
retrieval will hand it to the agent verbatim. Open with what was actually visible: which
alert fired, what the dashboard looked like, which service was loudest.

**Keep the dead ends.** A real investigation checks three things that turn out to be
irrelevant before finding the one that matters. Those wrong turns are the most useful
thing in the document — they are what makes a retrieved incident a piece of experience
rather than a lookup table. Delete them and you have written a spoiler.

**No absolute timestamps. Ever.** Write `T+3m`, "about four minutes after the page", "once
cart stopped serving" — never `08:02:41`. Two reasons, and both are load-bearing:

- *A re-record orphans them.* Wall-clock times belong to one recording. Two bundles needed
  re-recording in a single evening, and every timestamp written into a narrative would
  have silently become a reference to an incident that no longer exists — text that still
  reads as fact. The manifest holds the wall clock and is regenerated with the recording;
  `incident.md` is preserved across re-records precisely because it is the one file a
  person wrote, so it must not contain anything a re-record invalidates.
- *They carry no information anyway.* A retrieved incident is read months later by an agent
  matching it against a live problem. That it happened at 08:02 on a Saturday tells the
  reader nothing. That the cascade reached seven services three minutes after the page
  tells them everything.

The generated template already renders its tables this way — offsets from onset for the
page, offsets from the page for everything after. Match it in the prose.

Never mention the injector, the scenario id, or the fault class inside the prose.

## manifest.json

Written by the recorder. Required keys:

| Key | Meaning |
|---|---|
| `origin` | `scenario:<id>` — the provenance stamp T4.1b's exclusion filter reads |
| `scenario_id`, `split`, `fault_class` | copied from the scenario, so a bundle is self-describing |
| `injection` | target, method, params — exactly what was run |
| `t_inject`, `t_alert_firing`, `t_revert`, `t_clear` | UTC timestamps |
| `seconds_to_alert` | detection latency; `null` if no alert fired |
| `alerts_at_fire` | every `alertname/service` firing at that moment |
| `window` | the span the metric captures cover |

A bundle whose `seconds_to_alert` is `null` is not necessarily wrong — some faults are
meant to be quiet — but it needs a note in `incident.md` saying so deliberately.

## Marking a scenario rehearsed

Set `rehearsed: true` in the scenario YAML **only** once `incident.md` is finished. The
guard tests read that flag: a rehearsed scenario must have a bundle, and a finished
`incident.md` must have no template comments left in it.

### First, check every expected_evidence item against the bundle

Before flipping the flag, walk the scenario's `expected_evidence` list and confirm the
bundle actually contains each item. Correct — or move — any item the world does not
produce.

This is not a formality, and rehearsal is the only point where it is discoverable. The
scenarios were authored from how the system *should* behave; the bundle is what it
*does*. An eval that scores an agent against evidence which does not exist measures
nothing: the agent cannot find it, loses the point, and the score reads as a reasoning
failure when it is a labelling error.

Three failure shapes to look for, all of them seen at least once:

- **The signal exists, but on a different telemetry type.** Most common by far. Check the
  traces before deleting an item — a service that records something on a span very often
  logs nothing at all.
- **The service is too quiet to produce it.** Several demo services log only a startup
  banner at their default level. Silence in `logs/` is not evidence of health.
- **The signal exists but not in the captured window.** Widen `--dwell`, or note the
  timing in the item so it is reproducible.

### Also check for alerts the world produced on its own

Look through `alerts_over_window` for **`ServiceHighLatency/cartservice`** that is not part
of the injected fault. `cartservice` p95 is bimodal — mean 22ms, with excursions to 353ms
and nothing injected, measured at roughly one per 29 minutes lasting ~105s (ADR-0012).

At ~20 minutes of world time per rehearsal, **roughly six such excursions are expected
across the nine remaining scenarios.** Most are too short to fire and will never appear.
One that runs long enough to clear the 180s `for` clause will appear in
`alerts_over_window` and look exactly like blast radius — a latency alert on a service the
fault never touched, at a plausible time.

If you find one:

- It is not blast radius. Do not write it into `incident.md` as part of the incident.
- Check `began_after_revert` first — that flag already separates recovery-phase alerts, and
  a healthy excursion can land on either side of the revert.
- Note it in the narrative only if a responder would have been misled by it, which is
  itself worth recording: a spurious alert during a real incident is a realistic thing for
  an investigation to have to dismiss.
- It means the excursion outlasted its measured 105s, which contradicts ADR-0012's single
  observation. Say so — that ADR is explicit that n=1 and wants confirming.

Corrections already made this way:

| Scenario | Item | What happened |
|---|---|---|
| `product-catalog-flag-failure` | `logs:` the failure is reported as a deliberate flag-driven path | Moved to `traces:`. `product-catalog-service` emitted one line in 4.75 hours — its startup banner. The demo records this failure with `span.SetStatus` and `span.AddEvent` and never logs it, so the item was unobtainable as written. |

Nothing else in the ten scenarios claimed log evidence from a service measured silent.
`flag-service-crashloop` is the one to re-check at its own rehearsal: it expects a repeated
startup line, which the stub does emit on every restart, but the restart cadence has never
been observed.
