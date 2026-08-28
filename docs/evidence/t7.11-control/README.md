# T7.11 — the control that did not page

T7.10 discarded `frauddetection-memory-squeeze`: no incident within 900s, against a recorded onset
range of 390–469s, on one of the three scenarios whose alert set did **not** change in the
re-record. The hypothesis on record was T7.1's kafka heap cap, since this scenario's page is a
`ServiceNoTraffic` on a Kafka consumer.

**It does not reproduce. The scenario is healthy, the control is intact, and the discard was the
host suspending mid-run.** The kafka hypothesis is not supported — though kafka turns out to have
a separate and worse problem, characterised at the end.

## Direct observation: two injections, no agent

`faultline-inject start`, then poll the alert state and the call rate every 20s. No model calls.

| | attempt 1 | attempt 2 | re-recorded bundle |
|---|---|---|---|
| injected | 16:42:49Z | 16:56:06Z | — |
| rate reaches 0, alert `pending` | **T+201s** | **T+201s** | — |
| alert `firing` | **T+382s** | **T+381s** | **T+390s** |
| reverted | 16:49:11Z | 17:02:27Z | — |

**Both reproduce the bundle, and each other, to within nine seconds.** The rule is
`sum by (service_name) (rate(calls_total[3m])) == 0` with `for: 3m`, so pending at T+201s predicts
firing at T+381s. Attempt 2 hit that exactly; attempt 1 missed it by one second.

The paging path is not marginal on this world. It is arithmetic, and the arithmetic holds.

## What actually happened in T7.10

**Prometheus still holds the window**, because T7.1 raised retention from 6h to 15d. This is the
first time that change has paid for itself: the run is four days old and would have been
unanswerable under the old setting.

Two queries settle it.

**The alert was on its way when the harness gave up.**
`ALERTS{alertname="ServiceNoTraffic", service_name="frauddetectionservice"}` over 08:50–09:25
returns exactly one series, `alertstate="pending"`, **from 09:11:00 to 09:15:30**. It never
reached `firing`, and it did not go pending until 09:11 — the run's 900s deadline expired at
roughly 09:08.

**The metrics store has a sixteen-minute hole, and it is not scenario-specific.** Counting
services reporting `calls_total`, minute by minute:

```
08:45 → 08:55   15 services
08:56 → 09:10   (no samples at all)
09:11 → 09:12   15 services
```

**All fifteen services vanish together and return together.** Nothing about
`frauddetectionservice`, Kafka, or the injected fault can produce that shape — a fault on one
service does not stop the other fourteen from being scraped. The host suspended.

So the sequence was: inject at 08:53:44 → host suspends around 08:55 → deadline passes unnoticed
at ~09:08 → host resumes at 09:11, Prometheus sees no traffic and the alert goes pending
immediately → harness has already given up and reverted → traffic returns and the alert clears at
09:15:30 without ever firing.

**The scenario would have paged.** It was roughly three minutes from firing when the run stopped
waiting.

## The kafka hypothesis, tested directly and not supported

The mechanism proposed was that T7.1's heap cap changed Kafka throughput, moving when
`frauddetectionservice`'s rate window empties. Two observations refute it:

1. **The alert path is unchanged.** Both attempts fired within nine seconds of the bundle recorded
   under this same world and this same heap cap. If the cap had moved the timing, the bundle would
   have moved with it — the bundle was recorded *after* the cap.
2. **The failure was not scenario-shaped.** All fifteen services stopped reporting together, which
   no Kafka-consumer effect explains.

## A separate kafka finding: the heap cap did not stop the growth

Not the discard's cause, and worse than the thing it was meant to fix.

| | |
|---|---|
| heap cap in effect | `KAFKA_HEAP_OPTS=-Xmx400m -Xms400m` — confirmed on the running container |
| container RSS | **1866 MiB of 2048 MiB — 93.3%** |
| PID 1 RSS | 1868 MiB, **4.7× the heap cap** |
| measured shortly after T7.1's rebuild | 585 MiB (28.6%) |
| elapsed | ~14.5 hours |

**The cap works and does not matter.** It bounds the Java heap; the growth is outside it. Kafka
mmaps its index files and the page cache for its log segments counts against the container's
memory cgroup, and no `-Xmx` can bound either.

T7.1 predicted a cap would stop the growth that a limit raise only deferred. **That prediction was
wrong, and this is the measurement that says so**: 585 → 1866 MiB in ~14.5 hours is the same shape
CATALOG.md recorded before the cap (1200M → 2g, reaching 90.2% in about nine hours). Two points,
not a curve — but the endpoint is the one that matters, and it is already past the rehearsal
pre-flight gate's 90% threshold.

**The fix is not another cap.** It is bounding what Kafka retains — `log.retention.bytes` and
`log.segment.bytes`, so there is less on disk to map and cache — or accepting that kafka is
cycled between batches, which is what CATALOG.md's operational section already prescribes.

**It is digest-locked and does not land here.** The change edits the compose files that feed
`world.compose_digest`, so it would invalidate all twelve bundles and require another uniform
re-record. It queues with the other digest-locked changes.

**Meanwhile the world is above the gate threshold**, so the next rehearsal will be refused until
kafka is cycled. That is the pre-flight gate working, and the documented remedy — `docker restart
kafka`, then the consumers, which do not reconnect on their own — still applies.

## What it means

**For the S6 table:** `frauddetection-memory-squeeze`'s discard was **environmental, not a result**.
It is not evidence about the world change, the agent, or the scenario. S6 stands as six scored
runs, and the honest reading of the seventh is "the host slept", not "the control failed". The
scenario's own status as a control is intact — its alert set did not change and its paging
behaviour is unchanged.

**For the catalog's health:** the scenario is fine and the catalog is fine. What is not fine is
kafka, on a trajectory that will trip the pre-flight gate roughly daily until the retention change
lands. Every rehearsal and every scored run passes through that gate, so this is a standing tax on
the whole catalog rather than a problem for one scenario.

**A harness observation, recorded not fixed:** a suspended host is indistinguishable, from inside
the harness, from a world that will not alert — both look like a deadline expiring with no
incident. The 16-minute telemetry hole is visible in Prometheus afterwards and invisible to the
run at the time. A correlate-wait that noticed its own metrics had stopped could say "the world
stopped reporting" instead of "the fault did not fire", which are different findings and currently
produce the same discard message.
