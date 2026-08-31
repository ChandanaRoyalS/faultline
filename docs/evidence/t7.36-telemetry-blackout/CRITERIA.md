# T7.36 — disqualification criteria for D5, `payment-telemetry-blackout`

**Written and committed before the world was touched.** A scenario whose criteria were adjusted
after the probe is a scenario that chose its own result.

## The candidate

`bad_config` · target `paymentservice` · mechanism `BadConfigFault` (generic `env_var`/`value`,
the same machinery `cart-redis-misconfig` uses: a generated, uncommitted compose override plus a
recreate, so **no digest moves**).

**Repoint `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` at a dead address.** Traces only — *not* the metrics
endpoint, and the reason is the whole design:

- `calls_total` is produced by the collector's **spanmetrics** connector, so killing spans kills the
  traffic metric and `ServiceNoTraffic` becomes reachable.
- `OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` is a **separate variable and is left alone**, so the
  service's own runtime series keep flowing.
- Logs travel by promtail's `docker_sd_configs` over the docker socket, **independent of OTLP**, so
  they keep flowing too.

**The premise: the service is healthy, serving, and invisible in the traffic metric.**

## Magnitudes, in order

| # | value for `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` | why |
|---|---|---|
| **V1** | `http://127.0.0.1:4317` | nothing listens on the container's own loopback, so export fails fast and spans are dropped rather than buffered |
| **V2** | `http://blackhole.invalid:4318` | only if V1's fast-fail causes the SDK to block or buffer instead of dropping — a DNS failure fails differently |

**Two variants, then stop.** There is no V3 and no switching to another service. Three candidates
have already been disqualified in this project after passing a gate on paper, and the failure mode
each time was continuing to adjust until something passed.

## Check order — stop at the first failure

### 1. Does anything alert? *(first, not last)*

**Expected: `ServiceNoTraffic` on `paymentservice`, and nothing else.**

Mechanism, confirmed against the committed rules before probing: `ServiceNoTraffic` needs
`rate(calls_total[3m]) == 0` **with the series present**, plus
`rate(calls_total[30m] offset 10m) > 0`. Killing spans stops spanmetrics for that service while the
30-minute lookback still shows it serving. Confirmed empirically from two recorded bundles where a
service stopped exporting: `cartservice` fired `ServiceNoTraffic` for **4.0 min**
(`cart-bad-image-tag`) and `frauddetectionservice` for **5.8 min** (`frauddetection-memory-squeeze`).

**No error or latency alert is expected anywhere**, because nothing is failing or slow.

> **DISQUALIFY if no alert fires within the correlate budget (900s).** D5 then dies exactly as the
> "wrong but working" deploy did, the discard is recorded with the reason, and the budget is **not**
> extended to find one.

### 2. What does reachability say under the fault? *(the dangerous one)*

Reachability counts exactly two classes: **`runtime`** (`metrics/runtime.json`, the target's own
OTLP-exported SDK series, keyed on `exported_job`) and **`logs`** (≥ `TALKATIVE_LINES` = 10 lines).
`none_can_answer` is true only if both are empty.

**Expected: both answer.** Runtime survives because the metrics endpoint is untouched; logs survive
because promtail reads the docker socket. ADR-0005 measured `payment-service` at **1,128 lines/h**,
so a ~7-minute window is ~130 lines, comfortably above 10.

> **DISQUALIFY if `none_can_answer` is true.** A scenario that removes its own evidence is not a
> triumph of design — an excused failure is not a scored one.
>
> **This is verified against the recorder's own derived field, not reasoned about.** T7.22 produced
> a false `none_can_answer: true` on a bundle holding 126 log lines by deriving reachability before
> the captures were written, and it failed in the worst possible direction.

### 3. Does the remediation identify the class?

Restoring the endpoint is a config revert, which is `config_revert`, which puts the scenario in
`bad_config`. **The free slot is `bad_config-4`, and it is `dev`** — checked against T7.35's frozen
record rather than against T7.34's audit, which predates the freeze.

> **DISQUALIFY if restoring the endpoint does not restore telemetry within
> `RECOVERY_TIMEOUT_SECONDS` (420s).** A fault whose labelled remediation does not clear it is
> mislabelled, and ADR-0022 scores the class by which remediation works.

## The other conditions for abandonment

Stated now so none of them can be softened later.

4. **The service must stay healthy.** If repointing traces makes `paymentservice` error, slow down,
   or restart in a loop — for instance if the SDK blocks on a failing export rather than dropping —
   the premise is void: it is no longer healthy-and-invisible, it is just broken. **Disqualify.**
5. **Callers must stay clean.** If `checkoutservice` shows errors or raised latency, the scenario is
   no longer distinguishable from a genuine payment outage and it stops testing what it exists to
   test. **Disqualify.**
6. **The discriminator must exist in reachable evidence.** At least one of — runtime series present
   through the fault window, or target logs showing request handling during it — must hold. **If
   neither holds, disqualify**, because the evidence then cannot separate *alive but unobserved*
   from *dead*, and a benchmark item whose right and wrong answers are indistinguishable in the
   evidence is not scoreable. This is the criterion that decides whether D5 is worth building at
   all, rather than merely possible.

## What is not being done here

**The agent is not run against this.** Gating and recording are not agent exposure; scoring it is a
separate task with its own money.

## World protocol

One driver. **kafka recycled before recording**, which the gate now enforces (T7.31–T7.33), and
`accounting-service` restarted after any kafka cycle (T7.27). World left healthy.
