# RESULT - T7.2 re-check of the adapter's fixes

Read against [`PREREGISTRATION-T7.2-adapter.md`](../../runs/PREREGISTRATION-T7.2-adapter.md),
Addendum 4's re-check, and its Addendum 5. Run 2026-10-03, 06:31-07:20 UTC, at `6737776`. Evidence
is in [`docs/evidence/t7.2-recheck/`](../../../docs/evidence/t7.2-recheck/). **Never scored.**

## The three attempts, Faultline alone

| # | problem | judged | start to exit | what happened |
|---|---|---|---|---|
| r1 | `edge_request_filter_cpu_saturation` (shop) | 33 | 10.8 min | **triage judged the incident noise and gated it before fan-out**: no specialist ran, no tool was called, and the submission was `Faultline reached no verdict.` |
| r2 | `update_incompatible_correlated` (hotel) | **89, correct** | 10.4 min | `change_history` returned the fault itself: `mongo:4.4.6 -> mongo:8.0.14-rc0` on each MongoDB |
| r3 | `k8s_target_port-misconfig` (social) | 11 | 14.0 min | every tool answered, and none was asked about `user-service`, the faulty one |

- **r1's opening** fired `ServiceHighErrorRate` on `load-generator` alone, after two evaluations.
  The pilot's attempt 1 also had the startup crash loop on `product-catalog`, and this time it did
  not fire.
  - Triage read one synthetic service alarming as a harness artefact, with high confidence.
  - **That is Faultline's own gate** (T3.1), not the adapter. It is the real agent's behaviour,
    and a scored attempt that ends this way is a fail, as registered.
- **The same problem scored 22 in the pilot**, when every change query failed.
- **r3**'s two log queries came back empty and truncated. `get_logs` returns the newest 100
  lines, and they all fell after the window. That is SREGym's limit, stated in `McpToolSet`.

## The pass conditions

| condition (Addendum 4) | held? |
|---|---|
| every `change_history` call returns records or a true empty | **held**: 4 of 4 returned records, none truncated (r2: 10, 7 and 7 changes; r3: 3) |
| every log call accepted | **held**: 5 of 5, against 0 of 5 in the pilot |
| no tool call takes over 5 s | **not held as written**: two `change_history` calls took 6.4 and 5.5 s, the third 2.9 s. Every other call took 0.12 to 1.6 s. **Corrected by Addendum 5** (below), after the result |
| the opening on Social Network ends inside eight minutes | **held**: 5.1 minutes, through six evaluations to the fallback, against the pilot's 17.1 |

**Why the third failed, and what Addendum 5 records.**

- The condition was written to catch F3's defect, one keep-alive interval per MCP request.
- F2 made a `change_history` call issue up to eight requests, each running `kubectl` on SREGym's
  side, and nobody re-read the condition against that.
- Measured per tool call, **the defect is gone**. A one-request tool took 0.12-1.6 s, where the
  pilot's every request took 15.0-15.4 s. The slowest change call, eight requests in 6.4 s, would
  have taken about 120 s in the pilot.
- **The owner decided to correct the limit and go on**: *each MCP request under 5 s*. It is
  recorded as a correction made after the result, not as a pass.

## Also read

- **Install in the box**: 58, 64 and 60 s.
- **The probe beside r1 read nothing.** It waits five minutes after Loki first answers, and r1
  ended before that, because triage gated it. So the shop's selectors and Hotel Reservation's p95
  were not read live.
  - The selectors were read on r2 and r3 instead, 5 of 5 accepted.
  - **Hotel Reservation's p95 is still not established.** No attempt asked for it.
- **The world**: MemAvailable at least 5.12 GiB, no alert, no world container restarted since the
  pilot, no incident.
- **Spend**, from the recorded tokens at the published prices:
  - r2 $0.88 and r3 $0.56;
  - r1 one triage call, under $0.05, not persisted, since no trajectory was;
  - three judge calls, counted at $0.10 each.
  - **About $1.80 of the run's $50 cap.**

## Next

The scored run's operation, registered before it runs: 33 problems, both arms, the cap's tally
after each attempt, each Faultline attempt's record, and the close.
