# The span that was not latency — 2026-09-22

**\$0, no model call.** The v2 world's first usable quiet baseline
([`20260922T071933Z`](../../../evals/baselines/20260922T071933Z/)) passed its pre-registered
criterion: **one alert in 45 minutes, on the one service predicted in advance.** This note is what
that prediction turned out to be about, and what it changed.

## The result first, because it is the point

| | 04:41 (`[2m]`, 5 users) | 07:19 (`[5m]`, 25 users) |
|---|---|---|
| worst error ratio | **100.00%** (`recommendation`, `product-reviews`) | **2.22%** (`fraud-detection`) |
| services reporting 15000 ms p95 | **six** | **one** |
| highest p95 excluding `accounting` | 2653 ms (`flagd`) | **98 ms** (`fraud-detection`) |
| alerts | 2, flapping | 1, steady, predicted |

**The load raise and the window widening together did what neither did alone**, which is what the
first baseline's addendum predicted and refused to claim without measuring.

## `15000` was never a number

**The spanmetrics connector's bucket boundaries, read off the series rather than from the
documentation:**

```
[2, 4, 6, 8, 10, 50, 100, 200, 400, 800, 1000, 1400, 2000, 5000, 10000, 15000, +Inf]
```

So `histogram_quantile` returning **15000 means the p95 landed in `+Inf`** and Prometheus clamped
to the highest finite edge. It is not "15 seconds"; it is "above 15 seconds, unknown". And the
same applies at the bottom: **eight services in that summary report exactly `2 ms`**, which is the
lowest boundary and means "below 2 ms, unknown".

**A third of the rows in that table are edges of the instrument rather than measurements**, and
the table does not say so. Every previous reading of "flat at the ceiling" in these notes should be
read as "off the top of the scale", which is a weaker claim than the one that was made.

## What `order-consumed` is

`accounting`'s p95 broken out by span, on the quiet world:

| span | kind | p95 | rate |
|---|---|---:|---:|
| `order-consumed` | INTERNAL | **15000 ms** | 0.154/s |
| `orders receive` | CONSUMER | 98 ms | 0.154/s |
| `postgresql` | CLIENT | 2 ms | 0.154/s |
| `CONNECT otel` | CLIENT | 6 ms | 0.004/s |

**One span, and not the one that receives from Kafka.** From the demo's own
`src/accounting/Consumer.cs`:

```csharp
while (_isListening)
{
    using var activity = MyActivitySource.StartActivity("order-consumed", ActivityKind.Internal);
    var consumeResult = _consumer.Consume();      // blocks until a message arrives
    ProcessMessage(consumeResult.Message);
}
```

The activity opens **before** the blocking consume, so its duration is the wait for the next order.
`orders receive` is the auto-instrumented Confluent.Kafka span, created once a message has actually
been delivered — which is why it is healthy at 98 ms while the manual span around it is off the
scale. The two coexist and measure different things.

### The arithmetic, which was not available before and is the strongest part of this

**Order arrivals are near-Poisson, so inter-arrival times are near-exponential and the p95 is about
three times the mean** (−ln 0.05 ≈ 3.0), not the mean:

| | order rate | mean gap | predicted p95 | observed |
|---|---:|---:|---:|---|
| 5 users | 0.078/s | 12.8 s | **38 s** | `mean = min = max = 15000` |
| 25 users | 0.154/s | 6.5 s | **19.4 s** | mean 13853, dipping to 10750 |

Both predictions sit above the 15 s ceiling, which is why the first capture was pinned flat and the
second only occasionally falls into the 10–15 s bucket. **The arithmetic comes from the source and
the measured order rate; it was not fitted to the observations**, and it explains the thing the
earlier "waiting for work" account could not — why the duration *exceeded* the inter-arrival time
rather than equalling it.

**An earlier draft of this analysis doubted the original diagnosis** on the grounds that
`orders receive` was healthy. The source settles it the other way: the first baseline note's
account was correct as written, and the doubt was the error. Recorded because a doubt that is
resolved in favour of the original claim is still part of how the claim was established.

## The fix, chosen by measurement between three options

| | `order-consumed` | `orders receive` | `postgresql` | services kept |
|---|---|---|---|---|
| exclude `span_name="order-consumed"` | dropped | kept | **kept** | 18 |
| `SERVER\|CONSUMER` only | dropped | kept | dropped | **17** — `load-generator` lost |
| **exclude `SPAN_KIND_INTERNAL`** | dropped | kept | **kept** | **18** |

**The third.** It drops the background loop, keeps `accounting` genuinely observable — including
its Postgres client span, which is where a slow database on that service would show — loses no
service, and states a principle instead of a name: **an internal span is bookkeeping or a
background loop. It is either already inside an enclosing request span, or it is not request work
at all.**

The second option was the one this analysis initially preferred, on the grounds that a latency SLO
is about work done for a caller. It was wrong for `accounting` specifically: its inbound span is
the Kafka delivery, and its real work happens *after* that span closes. Restricting to inbound
spans would have made a slow database there undetectable — **the opposite of what that option was
chosen for**, and it was caught by listing what each option actually kept rather than by arguing
about principles.

**Scoped to latency only.** `ServiceHighErrorRate` and `ServiceNoTraffic` still see every span: an
error on an internal span is a real failure, and no internal span produced a false error — the
defect was specific to duration. `test_the_other_two_v2_rules_deliberately_see_every_span` pins
that so a later change made for symmetry has to argue for itself.

**What it costs**: a fault that slows only an internal span is invisible to this rule. No fault
class in ADR-0029 has that shape, and a service made slow by one would still show it on whichever
request span encloses the work.

## The thresholds are now measured here, and they carry a floor

`alert-rules-v2.yml` has said since it was written that 5% and 250 ms were inherited from v1 and
**were not evidence on v2 until measured there**. They are now:

| | healthy max | threshold | headroom |
|---|---:|---:|---:|
| error ratio | 2.22% (`fraud-detection`) | 5% | **2.25×** |
| p95 latency | 93 ms (`fraud-detection`) | 250 ms | **2.68×** |

v1's equivalents were 0.000% and 1.9–9.6 ms. **v2 is a noisier world at the same thresholds**, and
the consequence should be read as a property of the benchmark rather than a defect to tune away:
**a fault that lifts a service's error ratio to 4%, or its p95 to 200 ms, does not fire here and
never will.** Lowering the thresholds to catch it would buy that floor back with false positives on
a world whose quiet state already reaches 2.22%.

## One reading caveat about the summary itself

The error-ratio table lists **8 services** and the latency table lists **18**. That is not missing
data. The error ratio is a division with `by (service_name)` on both sides, so a service that has
emitted no `STATUS_CODE_ERROR` span has no series on the numerator and is dropped by the vector
matching. **Absence from that table means no errors** — the opposite of how it reads.

## Found while looking for somewhere to put a live check: the gate is blind on v2

Two of the three options above could in principle make a service disappear from a rule silently, so
this analysis went looking for the pre-flight gate to add a live check to. **The gate cannot
currently see the v2 world at all.**

`evalharness.gate` reads `METRIC_QUERIES["latency-p95"]` and `METRIC_QUERIES["call-rate"]` — the
**v1 constant**, hard-coded. On v2 those name `latency_bucket` and `calls_total`, which do not
exist, so both return empty. Following the code:

- `p95_over_ceiling` is empty → **no refusal**;
- `rates` is empty → `services_reporting = 0`, `silent_services = []` → **no refusal**.

**On the v2 world the gate approves anything.** It would record `services_reporting: 0` into the
manifest and refuse nothing on the strength of it. The checks that survive are the world-agnostic
ones: firing alerts, container uptimes, injector status, open incidents, the pipeline, headroom.

**Not fixed here**, because it is a different defect in a module this migration has not touched yet,
and folding it into a rule change would make both harder to review. It is the next patch, and it
carries a one-line guard that would have caught this whole class: **refuse when
`services_reporting == 0`.** The gate already computes that number and never looks at it. A world
where nothing reports traffic is either dead or being asked in a language it does not speak, and
neither is fit to inject into.
