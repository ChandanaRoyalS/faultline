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

Two rules, and they are the difference between a corpus that teaches and one that cheats:

**Write it from the responder's chair, not the author's.** You know the root cause because
you injected it. The person the corpus is simulating did not. If the narrative opens with
"the flag service was deployed with a broken image", you have written an answer key, and
retrieval will hand it to the agent verbatim. Open with what was actually visible: which
alert fired, what the dashboard looked like, which service was loudest.

**Keep the dead ends.** A real investigation checks three things that turn out to be
irrelevant before finding the one that matters. Those wrong turns are the most useful
thing in the document — they are what makes a retrieved incident a piece of experience
rather than a lookup table. Delete them and you have written a spoiler.

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
