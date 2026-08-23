# Scenario catalog — measured properties

What the scenarios turned out to be, as opposed to what they were designed to be. Each
section is written from committed bundles, after rehearsal. Nothing here is a proposal.

See `SCHEMA.md` for the file format, `SPLIT.md` for the dev/holdout allocation, and
`ARTIFACTS.md` for what a rehearsal bundle contains.

## Read every timing in this document as one sample

**Every `seconds_to_alert` in every bundle is a single draw from a distribution nobody has
characterised.** Treat detection times as observations, never as properties of a scenario.

The only scenario recorded twice is `cart-bad-image-tag`, and its two runs — same world,
same `compose_digest`, same `ffs_stub_source_digest`, same fault — measured **197s and
301s**. A spread of 104 seconds, 53% of the smaller value, on one scenario against an
unchanged world.

That is wider than any between-scenario difference this catalog reports. Every comparison
of one scenario's onset against another's is therefore reading noise unless it exceeds
about two minutes, and none of them do.

**The honest limit: n=2 for one scenario, n=1 for every other.** Two samples cannot
describe a distribution. We do not know its shape, its spread, or whether 104 seconds is
typical or an outlier — only that it is wide enough to swamp the differences we had been
reading meaning into. Nothing here supports a claim about detection latency beyond "it
varies by at least this much".

Two rules follow, for T4.x and anything else downstream:

- **Do not treat a single recorded detection time as a property of a scenario.** It is what
  happened once.
- **Do not compare timings across scenarios without stating `n`.** With n=1 on both sides,
  a difference of under two minutes carries no information.

This applies to the `seconds_of_steady_state` and `seconds_to_settle` figures too, and to
the settle-time range in ADR-0009, which rests on three observations of one scenario.

## The cart discrimination pair

`cart-redis-misconfig` (bad_config, dev) and `cart-bad-image-tag` (bad_deploy, dev) were
designed as a pair: two faults on the same service that look the same from the outside and
are separable only by change history. Both are now rehearsed, so the claim can be checked.

### Measured overlap

| | `cart-redis-misconfig` | `cart-bad-image-tag` |
|---|---|---|
| injected | 11:49:47 | 16:07:17 |
| onset to page | **218s** (n=1) | **197s, then 301s** (n=2) |
| alerts at fire | 3 | 3 |
| | `ServiceHighErrorRate/checkoutservice` | *identical* |
| | `ServiceHighErrorRate/frontend` | *identical* |
| | `ServiceHighErrorRate/loadgenerator` | *identical* |
| `ServiceNoTraffic` set | 7 services, 2.5m each | **the same 7 services, 2.5m each** |
| | accountingservice, cartservice, currencyservice, emailservice, frauddetectionservice, quoteservice, shippingservice | *identical* |
| alerts over window | 11 | 13 |
| recovery-phase alert | `ServiceHighErrorRate/emailservice` | `ServiceHighErrorRate/emailservice` |

**The page is identical.** Same three alerts, same three services, same rule. A responder
paged by either fault receives the same message.

**The blast radius is identical.** The same seven services go quiet, for the same 2.5
minutes, in the same order.

**Onset-to-page does not discriminate these scenarios, and the data now says so directly
rather than by assertion.**

An earlier version of this section reported 218s against 197s and called the 21-second gap
small. `cart-bad-image-tag` has since been re-recorded against the same world and measured
**301s**. Its own two runs therefore span **104 seconds** — five times the difference
between the two scenarios, and in the opposite direction from the one the first comparison
suggested.

| | |
|---|---|
| between the two scenarios | 21s (218 vs 197) |
| within `cart-bad-image-tag` alone | **104s** (197 vs 301) |

Within-scenario variance exceeds the between-scenario difference several times over, so
onset carries no information about which fault was injected. Only the 301s run is still in
the tree; the 197s figure survives only in this write-up, which is its own reason not to
build on it.

### The only difference in the metrics, and why it does not help

`cart-bad-image-tag` carries two alerts the other does not:

| Alert | Duration |
|---|---|
| `ServiceHighLatency/frontend` | 0.5m |
| `ServiceHighLatency/loadgenerator` | 0.2m |

Both are one to two samples long. `cartservice` p95 is known to be bimodal on this world,
reaching 353ms unfaulted with excursions around 105s (ADR-0012), and these are far shorter
than that. **Treating them as a discriminator would be reading noise**: they are the right
order of magnitude to appear or not appear in either scenario on any given run, and one
recording of each cannot establish otherwise.

### Does the pair claim survive?

**Yes — and more completely than intended.** The two faults are not merely similar on the
alerting surface; on the evidence recorded they are indistinguishable on it. The design
goal was "separable only by change history", and measurement supports exactly that.

### What separates them is not in Prometheus

**Change history.** One changed an environment variable (`REDIS_ADDR` to a wrong port); the
other changed an image tag to one that does not resolve. Different artifacts, different
remediations — `config_revert` against `rollback`. Neither change is visible in any metric.

**Container state.** The two failures are mechanically different in a way that leaves
different traces outside the metrics:

| | `cart-redis-misconfig` | `cart-bad-image-tag` |
|---|---|---|
| container | exists, crash-looping | **never created** — the tag does not resolve |
| logs during fault | repeated startup + `Wasn't able to connect to redis` | silence |
| exit code | non-zero, repeatedly | none — no process ever ran |
| restart count | climbing | zero |

`cart-bad-image-tag`'s own log capture shows this directly: normal traffic until
`16:07:17`, then `Application is shutting down...` at the injection instant, then **nothing
at all for the entire 8-minute fault window** (3 lines in-window, all the shutdown itself),
then a clean start at `16:15:35` on revert — `Application started`, `Successfully connected
to Redis`. A clean stop followed by silence, not a service failing repeatedly.

**Caveat: that comparison is not available inside the bundles.** `cart-redis-misconfig`'s
log capture failed — Loki returned HTTP 500 during the recording, and the file says so
rather than appearing empty. The crash-loop evidence quoted above is from an earlier
recording of that scenario which has since been replaced. **As committed, the pair's only
in-bundle discriminator is missing from one half of it.** That is a gap in the evidence,
not in the scenarios.

### Consequence for T4.x

**An agent restricted to Prometheus cannot separate these two, by construction.** Not
"finds it difficult" — the alert set, the affected services, the durations and the onset
are the same, and the one metric-level difference is indistinguishable from known
background behaviour.

Separating them requires a tool that reads something else: container state, container
logs, or change history. This makes the pair a direct test of whether an investigation
reaches beyond metrics, and it means a scoring run in which both scenarios are answered
identically is evidence about the agent's *tooling*, not its reasoning.

It also means the pair is only as good as those tools. If change history is unavailable to
the agent at T4.x, these two scenarios are not a discrimination test — they are one
scenario scored twice, and at best an agent can be right about one of them by guessing.

## Detectability is a function of recovery time, not severity

Measured on `recommendation-service` while choosing a ceiling for
`recommendation-memory-squeeze`. It is a property of this world rather than of the
scenario, and it is worth more than the scenario is.

### A service dying every 36 seconds, invisible to the entire stack

At a **48m** ceiling the fault fires constantly. Restart count climbed **13 → 18 → 22**
across two three-minute windows — roughly one OOM kill every 36 seconds — with memory
pinned at **47.6MiB of 48MiB**.

Across a full 12-minute rehearsal the telemetry recorded:

| | |
|---|---|
| call-rate samples during the fault | **49 of 49 present**, none zero, minimum 0.41 req/s |
| latency-p95 samples | **49 of 49 present** |
| error ratio | **0.00** at every sample |
| alerts, any rule, any service | **none** |
| caller impact (frontend, productcatalogservice) | none measurable |

The only movement anywhere was the target's own p95, from 4.4ms to 13.1ms mean. Against a
250ms threshold that is 5% of the way to firing.

**A Python process restarts in a second or two.** Against a 15-second scrape interval and a
2-minute rate window, a gap that short never produces a sample. The service was absent
dozens of times and the observation stack recorded a continuously healthy service.

### The same mechanism, visible, on a JVM

`ad-memory-squeeze` uses the identical mechanism — `docker update --memory`, a ceiling
below the working set — on `adservice`, and fired five alerts.

| | `recommendation-service` (Python) | `ad-service` (JVM) |
|---|---|---|
| target call rate during fault | min 0.41, **never zero** | min 0.00, **26 of 34 samples zero** |
| target latency samples during | **49/49 present** | **8/34 present — 26 missing** |
| caller p95 | frontend 42.3ms, unmoved | frontend **960ms mean, 3564ms peak** |
| caller error ratio | 0.00 | **0.08 mean, 0.11 peak** — over the 5% rule |
| alerts | 0 | 5 |

Same fault, comparable kill rate, opposite visibility. The JVM is slow enough to restart
that its absence lands inside the observation window; the Python service is not.

### The consequence

**Detectability here is a function of recovery time against the observation window, not of
severity.** A service dying every thirty seconds can be completely invisible to this stack,
while a less frequent failure on a slower-starting runtime alerts five times. Nothing about
the fault's seriousness predicts whether it is seen.

Two things follow.

Any scenario tuned by "does it alert?" is implicitly tuning for restart latency. That is
why `recommendation-memory-squeeze` ships at **32m** rather than 48m: at 32m the container
is OOM-killed before startup completes, never reaches a serving state, and `docker ps`
reports `Restarting (137)`. The service is then genuinely absent rather than briefly away.
The number was chosen to cross a *visibility* boundary, not a severity one, and the catalog
comment says so.

**The 48m case is a candidate scenario for a later phase**, not a defect. A service being
OOM-killed every 36 seconds while every dashboard shows green is a real and serious failure
that current alerting cannot see. It needs signals this stack does not yet collect —
container restart counts, exit codes, cgroup memory events — and with them it would make a
sharp scenario precisely because the metrics say nothing. Recorded here so the observation
is not lost with the ceiling that produced it.

## The catalog's only cross-class trap

`shipping-wrong-image` (bad_deploy, dev, `bad_deploy-3`) is the one scenario where the
**symptom class and the remediation class deliberately disagree**. This is a property of
the scenario, not a labelling error, and it is recorded here so that nobody later
"corrects" it.

### What it looks like versus what it is

| | |
|---|---|
| observable signature | exit 137, OOMKilled, restart loop, memory pinned at the ceiling |
| the class that signature belongs to | **resource_exhaustion** |
| `fault_class` | **bad_deploy** |
| `expected_remediation_class` | **rollback** |

The ad service's image is deployed into the shipping service's slot. The image resolves,
so the deploy succeeds — nothing fails at release time. But the ad service is a JVM and
`shippingservice`'s ceiling is 120 MiB, sized for a Rust binary. Measured: the JVM starts,
the OpenTelemetry agent loads, then exit 137 in a restart loop.

Every container-level signal matches a memory-limit fault exactly. `recommendation-memory-squeeze`
and `ad-memory-squeeze` produce the same 137, the same OOMKilled reason, the same restarts,
the same memory at the ceiling.

### What separates them, and why it is only change history

**The memory limit never changed.** `compose/world-arm64.override.yml` is untouched;
`shippingservice` has the same 120 MiB it always had. What changed is the image reference,
and therefore the size of the workload inside the ceiling rather than the ceiling itself.

That distinction exists nowhere in the metrics. Both faults present as a service that stops
serving with a resource-shaped death. Separating them requires reading what changed — the
same discriminator the cart pair depends on, and the same consequence: **an agent
restricted to Prometheus cannot classify this correctly.**

The logs do carry one strong tell — a JVM starting and an OTel agent loading, in a service
whose logs have never contained either — but that is log evidence, not metric evidence, and
it identifies the wrong image rather than the wrong remediation.

### Why the wrong fix is attractive

**Raising the memory limit would stop the crash loop.** It is the obvious response to
`137` + `OOMKilled`, it is the correct response to the two genuine memory faults in the
catalog, and here it produces a *worse* state than the one it replaces: the container would
start and then serve the ad service's protocol on the shipping service's port. A service
that is up and answering incorrectly is harder to detect than one that is plainly down, and
the deploy that caused it stays in place.

This makes the scenario a test of whether an investigation distinguishes *stopping the
symptom* from *undoing the cause*. Both remediations "work" by the measure of the alert
clearing.

### Deliberate, and not to be reconciled

The temptation on reading the bundle will be to relabel it `resource_exhaustion` so the
symptom and the class agree. Doing so would destroy the only cross-class case in the
catalog and, worse, would assert that raising the limit is the correct fix.

`fault_class: bad_deploy` and `expected_remediation_class: rollback` are both correct and
are meant to disagree with the symptom. If T4.2 shows agents systematically classifying
this one as `resource_exhaustion`, that is the finding the scenario exists to produce — not
evidence that the label is wrong.

## World hazards

Properties of `./world` that affect rehearsal but belong to no scenario.

### kafka grows into whatever memory ceiling it is given

Raised from 1200M to **2g at ~10:40** because it sat at 99.5% of the old limit and the
rehearsal pre-flight gate refuses to start against a container above 90%. By **~19:30 it
had reached 90.2% of 2g** — roughly nine hours to consume the new headroom entirely.

**This answers the morning's open question.** When the limit was raised it was unclear
whether 1200M had been undersized or whether kafka simply grows to fill what it is given;
a single settled reading looks identical either way, which is why the trajectory was worth
measuring. It is **unbounded growth**, not undersizing. Note the contrast with
`paymentservice` and `quoteservice`, both raised the same morning: each settled *below* its
old ceiling (160MiB of 320M, 77MiB of 200M), which is what a genuinely squeezed container
looks like. kafka does the opposite.

**Raising the limit again buys hours, not headroom.** At ~9 hours per doubling of the
excess, another bump defers the gate by less than a working day and makes the eventual
reset more expensive.

### Operational fix: cycle kafka between rehearsal batches

```
docker restart kafka
# wait for it to come back healthy, then:
docker restart accounting-service frauddetection-service checkout-service
```

The consumer restarts are not optional. `accounting-service`, `frauddetection-service` and
`checkout-service` **do not reconnect on their own** after kafka cycles; leaving them alone
produces a world that looks up and silently is not, which is exactly the state the
pre-flight gates exist to keep out of a bundle.

Do this **between** batches, never during one — restarting four containers mid-rehearsal
writes a broad unrelated incident into whatever bundle is recording.

### The fix we are not taking, and why

The real fix is to cap the JVM heap for kafka in `compose/world-arm64.override.yml` so it
stops growing rather than being periodically reset.

**Not now.** That file is one of the three inputs to `world.compose_digest` (ADR-0014), so
editing it changes the digest and **invalidates every recorded bundle** — they would no
longer agree about the world they were recorded against, correctly, because they would not
have been. Mid-catalog that costs a full re-record of everything already captured.

Worth doing immediately **before** the next full re-record, when the bundles are being
regenerated anyway and the digest change is free. Recorded here so the opportunity is not
missed and the change is not made casually in between.

## Detection time scales with the target's traffic rate

Measured across nine alerting bundles. Detection time is not a property of the fault alone
— it depends on how fast the target is being called.

| Scenario | onset to first alert |
|---|---:|
| `shipping-wrong-image` | 2m49s |
| `ad-memory-squeeze` | 3m15s |
| `product-catalog-flag-failure` | 3m24s |
| `cart-redis-misconfig` | 3m38s |
| `cart-dependency-latency` | 3m45s |
| `productcatalog-dependency-latency` | 3m49s |
| `cart-bad-image-tag` | 5m01s |
| `recommendation-memory-squeeze` | 5m26s |
| **`frauddetection-memory-squeeze`** | **11m15s** |

Eight of the nine land between 2m49s and 5m26s. The ninth takes **more than twice the
slowest of them**, and the difference is traffic rate: `frauddetectionservice` serves
**0.099 req/s** against 1–10 req/s for every other target in the catalog.

The mechanism is arithmetic rather than anything about the fault. `ServiceNoTraffic` reads
`rate(calls_total[3m])` against a 2-minute-windowed baseline and holds for `for: 3m`. Fed
one call every ten seconds, those windows empty slowly and the for-clause starts late. The
fault fires immediately; the *rule* takes four minutes longer to agree.

### The consequence: a global timeout misreports sparse services as undetectable

`frauddetection-memory-squeeze` was recorded with `seconds_to_alert: None` and
`alerts_at_fire: []` — a bundle that reads, at a glance, exactly like
`currency-cpu-throttle`, which genuinely cannot alert. It is nothing like it. The alert
fired at +675s; the recorder's 420s wait had already ended.

**A fault on a sparse service is real, detectable, and slow**, and none of those three is
visible from `alerts_at_fire` alone. Two things follow:

- Scenarios carry `alert_timeout_seconds` where the default is too short. It is a rehearsal
  hint outside `injection`, so it does not enter `scenario_fingerprint` and is not compared
  against the injector catalog — two scenarios differing only in how long the world takes
  to notice are the same experiment.
- **An empty `alerts_at_fire` is not evidence of silence.** Check `alerts_over_window`,
  which covers the whole capture: if it is populated, the wait timed out and the bundle is
  valid. The guard requiring an `INVALID.md` for alert-free bundles now makes that
  distinction, and the recorder's timeout message says which case it hit.

This also bounds what the detection times above can be used for. They are one sample each
(see the caveat at the top of this document), and they are a function of load-generator
behaviour as much as of the fault — a different traffic profile would move all of them.
