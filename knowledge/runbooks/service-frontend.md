---
id: service-frontend
title: Service - frontend
origin: authored
applies_to: [frontend]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The shop's web tier. `kind: application`, `tier: edge`, owner `demo/storefront`, and one of the
three services in this world measured to exceed its own latency threshold while nothing is
wrong.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| outbound | `frontend -> productcatalogservice` | 4575 | sync |
| outbound | `frontend -> cartservice` | 1754 | sync |
| outbound | `frontend -> adservice` | 463 | sync |
| outbound | `frontend -> recommendationservice` | 444 | sync |
| outbound | `frontend -> checkoutservice` | 330 | unmeasured |

Five outbound, four `sync` and one `unmeasured`. `unmeasured` is not a weaker `sync`: it means
no recorded bundle ever broke that callee, so nothing measured says whether a checkoutservice
**failure** reaches frontend. The direction and the call count are measured; only the failure
propagation is not - and the kinds in this table are about failure propagation only. Latency is
a separate question, measured separately, and the section below records what was measured about
this edge.

**Read these as edge counts, not service totals.** 4575 is what frontend sends
productcatalogservice, which takes traffic from two other callers as well.

## Its one inbound edge is excluded, so the graph shows none

The only thing that calls frontend is `loadgenerator`, and ADR-0017 excludes that edge as the
synthetic client. The node that exclusion removes is **`loadgenerator`'s** - nodes come from
edges and that was its only one - so the catalog carries it as `artifact_only` rather than
letting it read as absent. Frontend keeps its five outbound edges and has no inbound row in the
table above.

The consequence for traversal: frontend is a root in the dependency graph. Upstream traversal
from anywhere below it reaches frontend and stops.

## The at-rest latency tail

**Measured over twelve hours at 15s resolution on a world at rest** (ADR-0025): frontend's
median p95 is 42.3ms, and 127 of 2398 samples were above the 250ms threshold, 94 of them above
1000ms, in excursions sustained past the rule's three-minute `for:` clause. Two episodes in the
census, lasting 3630s and 900s, shared with `checkoutservice` and `loadgenerator`; every other
service in the world recorded zero samples over threshold. Frontend's share of it is not its
own - it waits on checkoutservice, and reports checkoutservice's stall (`service-checkoutservice`
carries the measurement).

**So `frontend -> checkoutservice` carries latency even though the table above calls it
`unmeasured`.** The two statements are about different things and neither is loose: `EDGE_KINDS`
records whether a *failure* propagates, measured by breaking callees in recorded bundles, and
nobody has broken checkoutservice; ADR-0025 measured separately that frontend blocks on it for
*latency*. An edge can be unmeasured for one and measured for the other.

`ServiceHighLatency` is therefore firing on a true condition here, and the rule was deliberately
not changed. What absorbs it is the scoring gate: `KNOWN_TAIL_SERVICES` names these three, and
the gate **refuses** to inject during an excursion rather than exempting them, because a
pre-existing alert would otherwise land inside an injected fault's blast radius. Roughly one
attempt in eight is refused and retried.

**The consequence for a recorded incident:** because the gate will not start a recording while an
excursion is firing, a `ServiceHighLatency` on frontend inside an incident's window is not this.

## What can page for it

All three rules, evaluated per `service_name`, and frontend has series under both metric
families. Its SLO row is the world's standard: p95 250ms, error ratio 0.05, sourced from
`compose/prometheus/alert-rules.yml`. `alert-high-latency` and `alert-no-traffic` carry the
rules' own mechanics.

`loadgenerator` has its own `calls_total` series and pages on its own behalf, so a stopped load
generator shows as `ServiceNoTraffic` on both of them rather than on frontend alone.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. The allowlist records that callers see the connection
reset while the container recreates; frontend's only caller is the load generator, which the
graph does not carry as an edge. `world-warm-up-latency` covers what a recreated container's p95
does next.
