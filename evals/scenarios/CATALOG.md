# Scenario catalog — measured properties

What the scenarios turned out to be, as opposed to what they were designed to be. Each
section is written from committed bundles, after rehearsal. Nothing here is a proposal.

See `SCHEMA.md` for the file format, `SPLIT.md` for the dev/holdout allocation, and
`ARTIFACTS.md` for what a rehearsal bundle contains.

## The cart discrimination pair

`cart-redis-misconfig` (bad_config, dev) and `cart-bad-image-tag` (bad_deploy, dev) were
designed as a pair: two faults on the same service that look the same from the outside and
are separable only by change history. Both are now rehearsed, so the claim can be checked.

### Measured overlap

| | `cart-redis-misconfig` | `cart-bad-image-tag` |
|---|---|---|
| injected | 11:49:47 | 16:07:17 |
| onset to page | **218s** | **197s** |
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

**Onset differs by 21 seconds** — 218s against 197s. That is under two scrape intervals and
well inside the variance already observed across repeated recordings of a single scenario,
so it discriminates nothing.

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
