# T3.1 smoke — triage against a replayed incident

The captured T2.1 webhook deliveries replayed through the built pipeline —
**ingest → orchestrator → triage** — against live Redis and Postgres. No world, no injector, no
tools: triage holds none (ADR-0020), so nothing in this path queries Prometheus, Loki or Jaeger.

| | |
|---|---|
| input | `docs/evidence/t2.1-webhook/payloads.jsonl` — 8 Alertmanager deliveries, `cart-redis-misconfig` |
| services used | `faultline-redis-1`, `faultline-postgres-1` |
| stream | `faultline:t31-smoke` (its own, so the T2.2 stream is untouched) |
| result | 8 delivered → 8 published → 8 applied → **1 incident, 4 episodes** |

## Files

- **`triage-output.txt`** — the run, unedited.

## What ran

```
captured deliveries: 8
ingest published: 8 events to faultline:t31-smoke
orchestrator applied: 8 events
incident d435dbf2-…  state=resolved  episodes=4
   frontend             ServiceHighErrorRate   starts 10:34:30
   loadgenerator        ServiceHighErrorRate   starts 10:34:30
   checkoutservice      ServiceHighErrorRate   starts 10:34:45
   emailservice         ServiceHighErrorRate   starts 10:39:30
```

## Triage output

```
12 services, severity critical, start from frontend, 4 unmeasured edge(s) crossed
blast radius: 12 services (4 alerted, 8 graph-derived)

service                  reason            direction         presence         entered
frontend                 alerted           seed              present          10:34:30
loadgenerator            alerted           seed              artifact_only    10:34:30
checkoutservice          alerted           seed              present          10:34:45
emailservice             alerted           seed              present          10:39:30
accountingservice        unmeasured_edge   candidate_cause   present          -
adservice                sync_edge         candidate_cause   present          -
cartservice              sync_edge         candidate_cause   present          -
currencyservice          unmeasured_edge   candidate_cause   present          -
paymentservice           unmeasured_edge   candidate_cause   present          -
productcatalogservice    sync_edge         candidate_cause   present          -
recommendationservice    sync_edge         candidate_cause   present          -
shippingservice          sync_edge         candidate_cause   present          -

unmeasured edges crossed (4):
   checkoutservice -> accountingservice
   checkoutservice -> currencyservice
   checkoutservice -> paymentservice
   frontend -> checkoutservice
```

## Four things in that output worth reading

**`frauddetectionservice` is absent, and `checkoutservice` is a seed.** It is one hop from an
alerting service across an edge the graph shows exactly like the others — same parent, 286 calls
— and it is not in the radius, because that edge is measured `async`. This is the case ADR-0020
§6 named as the blocker: before the measurement, a graph-based triage would have put it in.
Every other `checkoutservice` callee is here; that one is not.

**`loadgenerator` is in the radius and is not the entry point.** It alerted, so dropping it
would report a service that alerted as one that was unaffected — it is present, carrying
`artifact_only` provenance. But `start_from` is `frontend`: `loadgenerator` is the synthetic
client, and three narratives open by setting it aside. It entered at the same second as
`frontend` and would have won a naive earliest-first rule.

**Eight of the twelve have no entry time, and that is the honest value.** They never alerted.
Inheriting a time from the service they were reached through would invent a fact; `alerting`
returns the four that ADR-0009's ground truth can score.

**Four unmeasured edges were crossed, and the count travels with the result.** Those services
are in the radius because excluding them would assert a measurement nobody made — and they are
flagged because including them is not one either. A third of the graph's edges have no
measurement, and any use of this radius quotes that.

## The `emailservice` case, live

`emailservice` appears here as a **seed** — it alerted, at 10:39:30, four minutes after the
others and after the revert. ADR-0020 §6 is exactly about this: under ADR-0016 the orchestrator
joins it to the incident, correctly, and under ADR-0009 the scorer excludes it from blast
radius, correctly, because it is damage the fix did.

**Triage does not do that exclusion and cannot.** There is no revert in production and the
orchestrator has no concept of one; `began_after_revert` is a field the *bundle* carries for
scoring. What triage does is make the exclusion possible — the entry time is on the member, so
a scorer holding the bundle can subtract it. That is why the contract is a set with entry times
rather than a flat list.

## What this smoke did not exercise

- **A live fault.** The input is a four-month-old capture replayed from disk. Nothing was
  injected and no world was consulted.
- **The world being down.** It happened to be running during this run. Nothing in the path
  touches it — triage holds no tools and neither ingest nor the orchestrator imports the tool
  layer — so the independence is structural rather than demonstrated by absence. A run with the
  world stopped would demonstrate it; this one argues it.
- **Scoring.** No comparison against `alerts_over_window` was made. T4.2 owns that, and it is
  where the `emailservice` distinction above stops being a design note and becomes a number.
- **The other eight roles.** Triage is the only one built.

## Reproducing

The script is in the commit that added this directory. It uses its own stream and dedupe-key
prefix, so it can be re-run without touching the T2.2 smoke's data, and it clears both first.
