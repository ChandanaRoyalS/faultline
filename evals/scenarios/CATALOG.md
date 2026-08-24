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

## No guard reads a sentence

`recorded_from` binds a narrative to the recording it describes, and a guard fails if they
drift apart. That is a check on *which* recording the prose belongs to. **Nothing checks
whether the prose is true of it.**

Measured: `cart-bad-image-tag`'s narrative asserted there were "no logs, no exit code, no
restart count" and that checking the logs "returns nothing, because nothing exists to have
written them". The bundle beside it holds 500 log lines. Every guard passed — the manifest
is self-consistent, `recorded_from` matches, the front-matter durations match, the captures
are continuous and complete. The contradiction was found by opening the file and reading
it.

This is the limit of mechanical verification here, and it is worth stating rather than
discovering. Guards can check that a number matches its source, that a file is named for
what it contains, that two artifacts agree. They cannot check that a paragraph describes
what happened. Narratives are the part of a bundle that has to be read.

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
onset carries no information about which fault was injected.

### Variance is a property of the fault, not of the world

`cart-redis-misconfig` has since been recorded six times, and its detection times are
almost constant:

| | |
|---|---|
| 08-23 06:03:51 | 165s |
| 08-23 06:38:03 | 166s |
| 08-23 07:40:38 | 166s |
| 08-23 08:16:35 | 166s |
| 08-23 11:49:47 | **218s** |
| 08-24 04:44:27 | 165s |

**Five of six land within one second of each other.** Against `cart-bad-image-tag`'s
197s/301s on two runs, that is a materially different variance profile on the same world,
the same target service and the same alert rule.

This supports reading detection variance as a property of the **fault mechanism**. A wrong
Redis port fails a startup check deterministically: the container fails at the same point
in its lifecycle every time, so the error rate crosses the threshold at the same offset. A
deploy onto an unresolvable tag depends on compose's image resolution and teardown, which
has no reason to take the same time twice.

**The 218s outlier is unexplained.** It is the 11:49 recording, 52 seconds above a
five-sample cluster that is otherwise flat to within a second, and nothing distinguishes it
in the manifests — same world digests, same params, same alert set. It is recorded here
rather than smoothed away; one unexplained sample in six is exactly the kind of thing that
looks like noise until it turns out to be a mechanism.

None of this weakens the caveat at the top of this document. It sharpens it: `n` is not
interchangeable between scenarios, and six samples of one fault say nothing about the
spread of another.

### The only difference in the metrics, and why it does not help

`cart-bad-image-tag` carries two alerts the other does not:

| Alert | Duration |
|---|---|
| `ServiceHighLatency/frontend` | 0.5m |
| `ServiceHighLatency/loadgenerator` | 0.2m |

Both are one to two samples long. **Treating them as a discriminator would be reading
noise** — a clean 45-minute baseline puts `cartservice` p95 at a flat 1.9ms with zero
excursions, so a one-sample blip carries no information: they are the right
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

**The discriminator is now in both bundles.** An earlier recording of
`cart-redis-misconfig` lost its logs to a transient Loki HTTP 500 and captured five
comment lines saying so; the re-record captured 500. Both halves of the pair now carry
their log evidence, and the comparison can be made from the committed tree.

What the two captures contain is the sharper form of the point the `bad_deploy` trio
makes: **the presence, absence and content of logs is itself evidence.**

| | `cart-redis-misconfig` | `cart-bad-image-tag` |
|---|---|---|
| container during the fault | exists, crash-looping | **never created** |
| log lines inside the fault window | the service logging its own failure, repeatedly | **3 of 500** — the shutdown at injection, then nothing |
| what the logs say | `Wasn't able to connect to redis`, naming the dependency | silence, bracketed by a clean stop and a clean start |

Note the shape of `cart-bad-image-tag`'s capture, because "logs nothing" is not quite
right and the difference matters. The file holds 500 lines — the capture window opens five
minutes before injection, so it is full of ordinary traffic — but only **three** fall
inside the fault window, all of them the container shutting down at `18:53:53`. The next
line is at `19:04:46`, one second after the revert. A clean stop, eleven minutes of
nothing, a clean start.

So the two are not "logs versus no logs". They are **a service reporting its own failure
versus a service that was not running to report anything**, and telling those apart means
reading where the lines stop rather than counting them. An investigation that greps for
errors finds them in one bundle and finds nothing in the other — and the nothing is the
finding.

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

## Runtime metrics reach Prometheus, and their absence is the signal

Measured on `ad-memory-squeeze` and `recommendation-memory-squeeze` against the live world.
This was an open question when the section above was written — it assumed the memory
scenarios' decisive evidence sat entirely outside the agent's reach. Part of it does not.

**Services' own runtime metrics do arrive in Prometheus**, through the OTLP pipeline rather
than a scrape: `process_runtime_jvm_*`, `runtime_cpython_*`, `process_runtime_go_*`,
`process_runtime_dotnet_*`. Nothing had to be added to collect them; they were already
there.

**They are attributable, under a label nobody would guess.** The service label is
`exported_job`, not `service_name` — Prometheus renamed the exporter's `job` label because
it collided with the scrape job's. So the selector is:

```promql
process_runtime_jvm_memory_limit{exported_job="adservice",type="heap"}
runtime_cpython_memory{exported_job="recommendationservice"}
```

Anything written against `service_name` — which is what every query in `queries.md` uses,
because the span metrics do carry it — silently matches nothing on these series.

**Under fault the series do not degrade. They vanish.** Two runtimes, two ceilings, same
outcome:

| | `ad-memory-squeeze` | `recommendation-memory-squeeze` |
|---|---|---|
| runtime, ceiling | JVM, 256m | CPython, 32m |
| series | `process_runtime_jvm_memory_*{exported_job="adservice"}` | `runtime_cpython_memory{exported_job="recommendationservice"}` |
| before injection | Eden 47 MiB, Survivor 5 MiB, Tenured 117 MiB, usage 31 MiB | rss 70 MiB, vms 1859 MiB |
| under fault | **no series at all**, across 330 s | **no series at all**, across 300 s |
| restart count over that window | 22 → 36 | 0 → 14 |

The restart counts are `docker` readings, not agent-visible ones, and are quoted only to
establish what the absence means: in both cases the process never survived long enough to
export.

### The useful consequence

**A service's own runtime series disappearing separates "no traffic because the process is
gone" from "no traffic because nobody called it."** `ServiceNoTraffic` cannot make that
distinction — it fires on an absence of calls and says nothing about why. The runtime
series can, and it is one PromQL query against a tool the agent already has.

That is a real gain for the three `resource_exhaustion` scenarios, whose narratives
otherwise reason from container state (`RestartCount`, `OOMKilled`, exit 137) that no agent
tool can reach.

### What it still does not give

**The cgroup ceiling is observable nowhere.** Not in any metric — the runtime series report
what the runtime asked for and got, never the limit the kernel enforces. Not in logs. And
`docker update --memory` is not a deploy, so a deploy-only change history cannot see it
either. The *root cause* of all three scenarios remains unreachable; what became reachable
is the *symptom*, one level sharper than before.

**It does not separate the memory scenarios from `shipping-wrong-image`.** That JVM dies
too, so its runtime series vanish the same way. The cross-class trap below is untouched by
this measurement, and still turns on change history.

**Absence of a series is weaker evidence than presence of one.** A series can also stop
because the exporter broke, the collector dropped it, or the label changed. It supports
"this process is not running" and not "this process was OOM-killed."

**The signal is conditional on the process never getting to live.** The series vanish when
the process cannot reach a serving state; they persist when it is killed just as often but
recovers fast enough to keep running. Both measurements above are the first case, on two
different runtimes and two different ceilings — so runtime is not the variable.

The other side of that line is the same service and the same mechanism: the 48m
`recommendation-service` probe in the section above was OOM-killed roughly every 36 seconds
and was back inside a second or two, and the whole stack recorded a healthy service —
49 of 49 call-rate samples present, none zero, no alerts. A process that keeps being killed
but keeps coming back keeps exporting, and this signal says nothing about it. *(Directly
measured there: the span metrics and the alert stream. The runtime series were not read in
that window, so "kept exporting" is an inference from a process that was demonstrably
serving — sound, but not the same evidence as the two measurements above.)*

So the boundary is not JVM versus Python and not one ceiling versus another. It is whether
the process gets to live, and the failure that hides from every other signal — frequent
death with fast recovery — is exactly the one this signal also misses.

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

### cartservice needs about four minutes to settle after being recreated

Measured. `cartservice` p95 decays from **~100ms to 1.9ms over about four minutes** after
its container is recreated, monotonically:

```
+0.8 min  100.0ms      +1.6 min   30.0ms
+1.1 min   90.0ms      +2.0 min    8.5ms
+1.3 min   50.0ms      +4.0 min    1.9ms  settled
```

**A p95 sampled inside that window is not a baseline reading.** Anything that recreates the
container starts the clock: a `bad_config` or `bad_deploy` fault on cartservice, its revert,
or a `make world-up`.

This is worth stating plainly because getting it wrong cost three rounds of corrections to
ADR-0012. Readings taken 0.8, 4.0 and 14.2 minutes after cart reverts were written up as
evidence that the service is bimodal and reaches 353ms unprompted. It is not and it does
not: the clean 45-minute baseline (`evals/baselines/20260824T033742Z`) measures 181
consecutive samples at 1.9ms, min and max alike, with `checkoutservice` flat at 35–39ms
against the 1060ms the contaminated capture reported.

**`productcatalog-dependency-latency`'s pre-injection window contains one of these
transients.** Its window opens 48 seconds after a `cart-bad-image-tag` revert, so its first
six samples of `cartservice` run 100 → 30ms before settling. It does not affect that
scenario — its target is `product-catalog-service` and the transient is on a different
service — but **its pre-window is not strictly quiet**, and anyone comparing pre-injection
windows across bundles should know which one that is.

The rehearsal recorder now refuses to start when any container has been up for less than
five minutes, which is the mechanical version of this note.

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

### otel-col does the same, and the gate caught it

Measured: after roughly a day up, `otel-col` sat at **291.7MiB of its 300MiB limit** —
97.2%, over the pre-flight gate's 90% threshold — and a rehearsal was refused on it before
anything was injected. Same shape as kafka: unbounded growth into whatever ceiling it is
given, invisible in any single reading, and it surfaces as a blocked rehearsal rather than
as anything that looks like a memory problem.

**The fix used was a cycle, not a limit raise.** `docker restart otel-col`, and the gate
passes. Raising the 300M at `compose/world-arm64.override.yml:51` would be the tempting
one-line answer and is now unavailable: that file is a `compose_digest` input, so editing
it invalidates every recorded bundle (ADR-0014). The limit that is too small is locked by
the same mechanism as the heap cap that would stop the growth.

**This one matters more than kafka's,** because `otel-col` is the path every metric and
every trace takes. Where a kafka OOM writes a spurious incident into the bundle, a collector
OOM would write a *hole* — a world that stopped producing telemetry rather than a service
that stopped serving. That consequence is reasoned, not measured: the gate has never let it
happen, which is the gate working. `test_metric_captures_have_no_holes` is what would catch
it after the fact, at the cost of the run.

### Operational fix: cycle kafka and otel-col between rehearsal batches

**Before a batch, check both ceilings and cycle whichever is near one.** Neither is a
scheduled chore — they are two containers that grow without bound, and both are
digest-locked until T7.1, so cycling is the only lever available.

```
docker stats --no-stream --format '{{.Name}}\t{{.MemPerc}}' kafka otel-col

# kafka, if it is near its ceiling:
docker restart kafka
# wait for it to come back healthy, then:
docker restart accounting-service frauddetection-service checkout-service

# otel-col, if it is near its ceiling:
docker restart otel-col
```

The consumer restarts are not optional. `accounting-service`, `frauddetection-service` and
`checkout-service` **do not reconnect on their own** after kafka cycles; leaving them alone
produces a world that looks up and silently is not, which is exactly the state the
pre-flight gates exist to keep out of a bundle. `otel-col` needs no such follow-up — the
SDKs reconnect — but it is the one to check first, because everything a bundle records
passes through it.

Do this **between** batches, never during one — restarting these containers mid-rehearsal
writes a broad unrelated incident, or a telemetry hole, into whatever bundle is recording.

### The fixes we are not taking, and why

The real fixes are both edits to `compose/world-arm64.override.yml`: cap the JVM heap for
kafka so it stops growing rather than being periodically reset, and raise `otel-col`'s
300M so a day of uptime does not trip the pre-flight gate.

**Not now, and not either of them.** That file is one of the three inputs to
`world.compose_digest` (ADR-0014), so editing it changes the digest and **invalidates every
recorded bundle** — they would no longer agree about the world they were recorded against,
correctly, because they would not have been. Mid-catalog that costs a full re-record of
everything already captured, and the cost is the same whether the edit is one line or two.

Both are worth doing immediately **before** the next full re-record, when the bundles are
being regenerated anyway and the digest change is free. Recorded here so the opportunity is
not missed and neither change is made casually in between.

**The queue for T7.1, in one place** — every change that is right, cheap, and locked until
the catalog is re-recorded against one world:

| Change | File | Why it is locked |
|---|---|---|
| cap kafka's JVM heap | `compose/world-arm64.override.yml` | `compose_digest` input |
| raise `otel-col`'s 300M limit | `compose/world-arm64.override.yml:51` | `compose_digest` input |
| raise Prometheus retention to 15d | `compose/telemetry.yml:66` | `compose_digest` input |

Note the trap in the first two: the pre-flight gate's own message suggests raising the
limit in `compose/world-arm64.override.yml`, which is the advice that was correct when it
was written and is now the one action that invalidates the catalog. Cycle the container
instead.

### Prometheus keeps 6 hours, and raising it invalidates the catalog

The demo pins `--storage.tsdb.retention.time=1h` (`world/docker-compose.yml:607`).
`compose/telemetry.yml:66` overrides it to **6h**, with the reason in a comment beside it:
the demo's hour is too short to investigate an incident after the fact.

**Six hours is the horizon, and it is locked.** `compose/telemetry.yml` is one of the three
inputs to `world.compose_digest` (ADR-0014), so raising the retention changes the digest and
**invalidates every recorded bundle** — the same trap as the kafka heap cap above, for the
same reason, on a different file. The setting that would let us look further back is itself
the thing that makes looking back at existing bundles impossible.

**This has already cost something once.** When the fifth capture was added, the obvious
tidy answer was to backfill `runtime.json` into the ten existing bundles rather than leave
a mixed catalog. It could not be done: the bundles' windows are all from 2026-08-23, the
Prometheus server started `2026-08-24T08:53Z`, and a query at `cart-dependency-latency`'s
`t_inject` returns no data. The window was gone before the question was asked. That is what
settled the decision recorded in `ARTIFACTS.md`, "The capture set changed, and the existing
ten are not being re-recorded".

**Queued for T7.1: raise retention to 15d**, at the same moment as the kafka heap cap and
the `otel-col` limit, and for the same reason — T7.1 re-records the whole catalog against
one world, so the digest change is free exactly then and expensive at any other time. Three
digest-locked changes now wait on that re-record, listed together under "The fixes we are
not taking, and why"; anything else discovered in the meantime should join that table
rather than be taken early.

**Until then, the practical rule.** Any question of the form *"what did X look like during
run Y"* has to be answered within **six hours** of the run, or from that run's own captures.
There is no third option, and the six hours are not a deadline anyone will notice passing.

This is a direct argument for the capture set. A bundle is not a convenience copy of data
that lives in Prometheus — after six hours it is the **only** record that the run happened
at all, which is why an under-captured bundle cannot be repaired later and why adding a
capture is worth doing at the moment the need is identified rather than at the next
re-record.

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

## The bad_deploy trio: absent, misleading, decisive evidence

The three `bad_deploy` scenarios are the same class of mistake — the wrong image in a
service's slot — and they were chosen so that the container's own logs are worth a
different amount in each.

| Slot | Scenario | Split | What the logs give you |
|---|---|---|---|
| `bad_deploy-1` | `cart-bad-image-tag` | dev | **nothing** — the tag resolves nowhere, no container is ever created, and there is no process to log |
| `bad_deploy-3` | `shipping-wrong-image` | dev | **the wrong answer** — a JVM dying on memory, exit 137, OOMKilled. Read literally it points at `resource_exhaustion` and at raising the memory limit |
| `bad_deploy-2` | `email-wrong-image` | **holdout** | **the answer** — Apache naming `QUOTE_SERVICE_PORT` as undefined, exit 1, in a service whose logs have never contained PHP |

### The intent

The two dev scenarios teach that logs are not where the answer lives. One has no logs at
all; the other has logs that confidently indicate the wrong fault class and a remediation
that would make things worse. An investigation tuned on the dev split — by prompt, by
retrieval, or by an agent generalising from past incidents in the corpus — has every reason
to arrive at the holdout treating container logs as a dead end.

**The holdout scenario is the one where the logs contain the answer outright.** It tests
whether the responder checks anyway.

### Rehearsal made the holdout harder than it was designed to be

`email-wrong-image` has since been rehearsed, and the alert set is narrower than expected.
**The entire incident produces one alert: `ServiceHighErrorRate` on `checkoutservice`,
firing 256s after injection and running six minutes.** `emailservice` never appears in the
alert stream at all — not `ServiceNoTraffic`, not anything.

So the scenario has a second layer nobody designed in. The alerting names a **healthy**
service, and never names the broken one. Reaching the decisive evidence requires following
a dependency from the service that alerted to the service that failed, and only then
reading its logs. An investigation that works from the alert alone lands on
`checkoutservice`, where there is nothing wrong and nothing to find.

The evidence is still decisive **once reached**. What changed is the cost of reaching it:

| | designed | measured |
|---|---|---|
| what alerts | the broken service, plus its callers | **only a caller** |
| first step | read the alerting service's logs | follow a dependency to a service that never alerted |
| the logs, once opened | name the cause outright | unchanged — still decisive |

That is a harder scenario, not a weaker one, and it stacks on the trio's original point: an
investigation that has learned from the dev pair to skip logs must now also work out
*whose* logs to open, with no alert pointing at them.

This is a deliberate use of the split rather than an accident of authoring. The dev set is
what anything gets tuned against (ADR-0008), so a heuristic learned there is exactly what
the holdout should be able to punish. "Skip the logs, they never help on bad deploys" is a
heuristic the dev pair actively teaches and the holdout inverts.

### What it does not test

It is one scenario, and a failure on it is ambiguous: an agent could miss it because it
learned to skip logs, or because it never reads logs at all. Distinguishing those needs the
per-class breakdown T4.2 already owes, plus the observation that the same agent found
`shipping-wrong-image`'s logs uninformative rather than absent.

### What the pre-rehearsal prediction got wrong

This section and the scenario's ground truth were both written **UNVERIFIED**, from a
five-minute probe, and said so. The rehearsal checked them. One particular was wrong, and
it is recorded here rather than quietly corrected — a prediction that was written down,
tested and partly falsified is worth more in the record than one that was edited to match
the result.

| Predicted | Measured |
|---|---|
| Apache naming `QUOTE_SERVICE_PORT` undefined, exit 1, PHP in a service that has never run it | **held** |
| `ServiceHighErrorRate` on `checkoutservice` within five minutes | **held** — 256s |
| `emailservice` stops emitting, and that absence is visible in the alerting | **wrong** — the absence is real in the metrics, but it produces no alert, and `emailservice` never enters the alert stream |

The premise this section was written to defend — that the logs are decisive — survived. The
supporting assumption about how a responder would be *pointed at* those logs did not, and
the scenario is harder than it was designed to be as a result.

The remaining caveat stands: this is one rehearsal, and its detection time is one sample
(see the caveat at the top of this document).
