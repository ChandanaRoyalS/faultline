# The v2 world's first quiet baseline — 2026-09-22, and the world is too quiet to measure

**45 minutes, 15 s step, nothing injected, \$0, no model call.** The first baseline ever taken on
the v2 world, through `python -m evalharness.baseline --world v2`
(`evals/baselines/20260922T044153Z/`). It exists because
[`alert-rules-v2.yml`](../../../compose/prometheus/alert-rules-v2.yml) says in its own header that
its thresholds are carried over from v1 and **are not evidence** until measured here.

**They are not merely unvalidated. They are unusable, and not because the numbers are wrong.**

## What the quiet world reported

**Two alerts fired on a world with no fault in it**, both `ServiceHighLatency/accounting`, for 28
minutes and then 2 minutes more — so it **flaps**, which is worse for a benchmark than a steady
false positive: a scenario's page would be nondeterministic.

| p95 latency, quiet world | mean | min | max |
|---|---:|---:|---:|
| `accounting` | **15000 ms** | 15000 | 15000 |
| `flagd` | 2653 ms | 2 ms | **15000 ms** |
| `fraud-detection` | 1569 ms | 2 ms | **15000 ms** |
| `ad` | 1552 ms | 2 ms | **15000 ms** |
| `recommendation` | 1532 ms | 2 ms | **15000 ms** |
| `product-reviews` | 1494 ms | 6 ms | **15000 ms** |
| everything else (12 services) | ≤ 45 ms | | ≤ 48 ms |

| error ratio, quiet world | mean | max |
|---|---:|---:|
| `recommendation` | 3.74 % | **100.00 %** |
| `fraud-detection` | 3.33 % | 33.33 % |
| `ad` | 3.10 % | 33.33 % |
| `product-reviews` | 3.04 % | **100.00 %** |
| `flagd` | 1.09 % | 10.00 % |

**`min 2 ms, max 15000 ms` is not a latency distribution**, and `33.33%` is one error in three.

## The cause, measured rather than inferred

Mean call rate over the same window:

| | req/s | samples in a `[2m]` window |
|---|---:|---:|
| `frontend` | 2.107 | 253 |
| `cart` | 0.754 | 90 |
| `product-reviews` | 0.153 | 18 |
| `ad` | 0.070 | **8** |
| `fraud-detection` | 0.052 | **6** |
| `payment` | 0.050 | **6** |

**Most of the world runs at one request every ten to twenty seconds.** A p95 over six samples is
the maximum; one slow span puts it in the histogram's top bucket, which is what 15000 ms is. One
error in six requests is 16.7 %, two is 33.3 %, and a window whose only recorded call failed is
100 %. **Every anomaly in the tables above is sampling noise on a single-digit denominator.**

**And the knob is in the demo's own `.env`:**

| | v1.2.1 | v2.2.0 |
|---|---|---|
| `LOCUST_USERS` | **10** | **5** |
| services emitting spans | ~10 | **18** |

**v2 halves the load and spreads it across roughly twice as many services.** That is the whole
distance between v1's baseline — *"error ratio 0.000 on every service, no sample above the 5%
threshold; p95 1.9–9.6 ms for most services"* — and this one.

## Why this blocks T7.1 rather than annoying it

The benchmark's premise is: inject a fault, an alert fires, the agent investigates what it finds.
**A world whose healthy state produces 33–100 % error ratios and 15-second p95s on six services
cannot support that**, because no rule can separate an injected fault from the noise, and no
scenario's recorded page would be stable across runs. Thirty scenarios authored against this world
would each inherit the problem.

**It would have been found mid-sweep**, after the catalog was written and the world re-recorded, at
a cost measured in days and dollars. It was found instead by 45 quiet minutes at \$0, because
`alert-rules-v2.yml` refused to call inherited thresholds evidence.

## The fix, and what is a hypothesis in it

**Raise the load rather than widen the windows or move the thresholds.**

- **Widening `[2m]` to `[10m]`** buys the same five-fold sample count for free in resources, and
  **costs detection latency**: the rules' `for:` clauses already put first-fire at four to five
  minutes, and the scenario loop carries a 300 s settle on top. Slowing the instrument to fit a
  thin world is fixing the measurement rather than the thing measured.
- **Raising the thresholds** fits the numbers and destroys their meaning: a 15000 ms bound would
  never fire on a real fault either.
- **Raising the load** restores the statistics without touching the rules, and leaves v1's
  thresholds comparable across the world boundary, which is worth something.

**The arithmetic, stated so the number can be checked:** a stable p95 wants on the order of **30
samples** in the `[2m]` window, which is **≥ 0.25 req/s**. The quietest service is at **0.050**, so
it needs **5×**. `LOCUST_USERS` 5 → **25** on a linear assumption.

**The linear assumption is a hypothesis and is not claimed as a result.** Locust users are
concurrent sessions, not request generators, and per-service rates depend on what each user's
journey touches — `payment` is hit once per checkout while `frontend` is hit on every page. **The
number is verified by re-baselining, not by arguing**, and if the quietest services still fall
short the figure moves again.

## What this baseline is, and is not

**It is not a usable baseline** and nothing may be scored against it. `alert-rules-v2.yml`'s
thresholds remain uncalibrated, and the twelve services under 48 ms are the only rows here that
mean anything — they are quiet because they are *busy enough to be quiet*.

**It is a measurement of the world's traffic**, which is what it will be cited for, and it is the
reason the load moves before anything else in T7.1 does.

**`accounting` is still a separate finding and survives the fix.** Its span opens *before* a
blocking Kafka consume (`Consumer.cs`), so its duration is time spent waiting for work; at
`mean = min = max = 15000 ms` it is not noisy, it is **flat at the ceiling**, and more load will
not move it. It needs an exclusion on the same argument that excludes `frontend-proxy` from
`ServiceNoTraffic` — but that is decided **after** the re-baseline, when it can be told apart from
everything else that is currently at 15000 ms for a different reason.
