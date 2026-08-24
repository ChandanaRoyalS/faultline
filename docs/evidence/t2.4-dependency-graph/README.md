# T2.4 evidence — the measured service dependency graph

ADR-0016 deferred `DependencyPolicy` to T2.4 and wrote down a prediction for it to check
rather than assume. This is the check, plus two findings that were not predicted and change
what a graph-based policy can be asked to do.

| | |
|---|---|
| source | `GET /jaeger/ui/api/dependencies` through frontend-proxy on `:8080` |
| captured | 2026-08-24T12:35:13Z |
| lookback | 24h (`endTs=1787574913000`, `lookback=86400000`) |
| covers | three `cart-redis-misconfig` injections — ~10:32, ~11:08, ~12:00 |
| result | 17 edges, 16 nodes; **15 edges, 13 nodes** after excluding two artifacts |

## Files

- **`dependencies.json`** — the API response, unmodified apart from pretty-printing.
- **`edges.txt`** — the same edges as a sorted table, with the artifacts marked.

The API path matters and is not the obvious one: `/jaeger/api/dependencies` through the
proxy returns the UI's HTML with a `200`, because Jaeger's query service serves the SPA for
paths it does not recognise. The working path is `/jaeger/ui/api/dependencies`. Anything
that fetches this and does not check `content-type` will parse an HTML page as an empty
graph and report a world with no dependencies.

## Two edges are artifacts of how the world is run

**`loadgenerator -> frontend` (5937 calls)** is the synthetic client. It is the largest edge
in the graph by a factor of three and it represents nobody. A blast-radius calculation that
counts it will rank `frontend` as the most-depended-on service in the world on the strength
of traffic we generate ourselves.

**`frontend-proxy -> jaeger-all-in-one` (5 calls)** is the tracing UI being routed to
through the proxy, traced by the proxy. `jaeger-all-in-one` is not a demo service; it is
the span store, appearing as a node because looking at traces makes traces.

Both are excluded from everything below. `jaeger-all-in-one` is also the one node name that
`injector.world.canonical_service` maps to nothing at all — worth knowing, because
`frontend-proxy` in this data *is* canonicalised, to `frontendproxy`. The graph's node names
are OTel `service.name` values, and they agree with compose service names in 12 of 13 cases.
Identity has to go through `canonical_service` here as everywhere else.

## Prediction 1 — confirmed

**ADR-0016 predicted that a graph rule would join `emailservice` to the cart incident via
`checkoutservice` as a common caller, two hops apart.** It said so before the graph existed,
so that it could be checked rather than assumed.

Measured:

```
   572  checkoutservice -> cartservice
   286  checkoutservice -> emailservice
```

Both edges exist. `cartservice` and `emailservice` are exactly **2 hops** apart through
`checkoutservice`. The prediction holds, and the recovery alert that ADR-0016's whole
correlation section is built around would be joined by a dependency rule as well as by the
time rule that ships today.

## Prediction 2 — confirmed, and it is a structural blindness

**`featureflagservice` has no node.** Not a node with no edges: no presence at all.

This is the same blindness already measured for alerting, now in the graph. From
`evals/scenarios/flag-service-crashloop.yaml:3`, which blocked that scenario:

> `featureflagservice` emits no span metrics. Verified against Prometheus:
> `count by (service_name) (calls_total)` returns 15 services and it is not among them […]
> Two of the three alert rules are scoped by `service_name` over `calls_total`, so
> `ServiceNoTraffic` and `ServiceHighErrorRate` cannot evaluate for this service at all —
> not "did not fire", but *cannot*.

The cause is the same: ADR-0006's stub reproduces the flag service's gRPC contract and none
of its instrumentation. A service that emits no spans cannot appear in a graph built from
spans, so **a graph-based policy is structurally blind to it** — it cannot be a node, cannot
be an endpoint of an edge, and cannot be on a path between two other services.

It is not alone. `kafka` and `redis-cart` are absent for the same reason, and both matter:
`kafka` is the broker two of `checkoutservice`'s edges pass through, and `redis-cart` is
`cartservice`'s datastore in the catalog's most-rehearsed scenario.

## Finding — the graph cannot tell a synchronous call from an asynchronous one

This was not predicted and it is the most consequential thing in the capture.

```
   286  checkoutservice -> accountingservice
   286  checkoutservice -> emailservice
   286  checkoutservice -> frauddetectionservice
   286  checkoutservice -> paymentservice
```

Four edges out of `checkoutservice`, identical call counts, identical shape. Two of them are
synchronous RPCs. Two are Kafka topics — `accountingservice` and `frauddetectionservice` are
the consumers named in `CATALOG.md`'s kafka-cycling note as the ones that never reconnect on
their own. **Trace context propagates through Kafka**, so the producer's span and the
consumer's span join into one trace, and the dependency job renders the pair as a direct
edge. The broker is not a node, so the hop through it is invisible.

**The catalog has already measured that these two edges behave in opposite ways under
failure.**

| | `email-wrong-image` | `frauddetection-memory-squeeze` |
|---|---|---|
| target | `emailservice` | `frauddetectionservice` |
| edge from checkout | sync | async, via kafka |
| what alerted | **`ServiceHighErrorRate` on `checkoutservice`** | `ServiceNoTraffic` on the target only |
| downstream impact | took checkout down; the broken service never alerted at all | **none measurable** |

The `frauddetection` bundle's narrative states the async consequence directly: "Orders were
being placed and not screened. The work was not failing — it was accumulating unprocessed,
and nothing in the alerting measures how much of it is waiting."

So: **the trace graph records call causality, not failure propagation.** An edge says *A's
work reaches B*. It does not say whether A waits for B, and therefore does not say whether
B's failure becomes A's. Two edges that are byte-identical in this capture produced opposite
incidents in the catalog, and nothing in the graph distinguishes them.

Anything reasoning about blast radius from this graph alone will conclude that
`frauddetectionservice` failing endangers `checkoutservice`. That is measurably false, and
the measurement is already in the tree.

## What the graph is dense enough to decide

A hop-radius correlation rule is the obvious use, and the graph's shape limits how much work
it can do. Over the 13 real nodes, all 78 unordered pairs:

| within | pairs | cumulative |
|---|---|---|
| 1 hop | 15 | 19% |
| 2 hops | 41 | **72%** |
| 3 hops | 20 | 97% |
| 4 hops | 2 | 100% |

`checkoutservice` has degree 9 and `frontend` degree 5 in a 13-node graph, so almost every
path runs through one of them.

**Only a 2-hop radius is usable, and it is weak.** 1 hop fails the measured `emailservice`
case that motivated the whole policy. 3 hops joins 97% of pairs, which is a rule that never
declines — indistinguishable in practice from the `TimeOverlapPolicy` it would replace. At 2
hops the policy declines 28% of pairs: a real filter, but a thin one, and worth stating as a
number before anyone describes graph-based correlation as precise.

## Reproducing

```bash
END=$(( $(date +%s) * 1000 )); LB=$(( 24*60*60*1000 ))
curl -sS "http://localhost:8080/jaeger/ui/api/dependencies?endTs=${END}&lookback=${LB}" \
  | python3 -m json.tool
```

Jaeger here is all-in-one with in-memory storage, so the graph exists only for as long as
the container does and only covers spans inside the lookback. A restart empties it, and a
quiet world thins it. That is the argument in ADR-0017 for committing a snapshot rather than
querying at runtime.
