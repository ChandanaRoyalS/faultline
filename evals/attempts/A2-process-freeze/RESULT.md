# A2 — process freeze `docker pause product-catalog` — RESULT

**Run 2026-09-22 14:20:23 → 14:42:02 UTC, \$0.** One run, `transcript.txt`. The verdicts are the
pre-registered definitions applied to the transcript and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes** | `ServiceNoTraffic/product-catalog` firing at 14:27:59 — **7 min 36 s** after the pause, on the target itself. `ServiceHighLatency/frontend`, the direct caller, at 14:26:59 (+6:36). The first alert anywhere was at 14:24:59 (+4:36): `ServiceHighErrorRate` and `ServiceHighLatency` on `frontend-proxy`, and `ServiceHighErrorRate` on `load-generator` |
| **DISTINCT from `bad_deploy` (crashloop)** | **yes, on (a), (b) and (c)** | **(a)** A paused process does not refuse connections; it accepts them into the kernel backlog and never answers. So its callers **hang** rather than fail: `frontend` at 0.00% errors and a p95 off the top of the scale, with its throughput collapsed from 11.3 to 2.3 req/s, and the errors surfacing one hop further up as Envoy's upstream timeouts (`frontend-proxy` 26%). A crashlooping container refuses, which is a fast error at the caller and no collapse. **The shape is hang-and-cascade versus refuse, and it is agent-visible in the alerts and the metrics.** **(b)** No change is recorded; a crashloop leaves the image change. **(c)** A frozen process cannot log: the target's log is empty; a crashloop logs its startup failure on every restart |
| **REVERTS** | **yes, with the window's last minute owed** | Unpaused at 14:32:26. Every alert cleared by 14:38:02 (**5 min 36 s**), within the ten. The window then held **four** quiet minutes, not five: 14:38:02–14:42:02. The fifth is satisfied by A3's pre-state check, which requires the world quiet and is run next; recorded here so the number is not rounded |
| **ADMISSIBLE** | **yes** | pages, distinct, reverts, and is a tool and a surface no existing mechanism has |

**Prediction scorecard.** PAGES: right. Rule on the target: right (`ServiceNoTraffic`).
**Callers: wrong** — I predicted errors on `frontend`; it slowed and did not error. The
registered uncertainty *"whether the callers error or merely slow"* resolved to *slow*, with the
errors appearing at `frontend-proxy`. **Timing: wrong** — predicted 3–5 min for `ServiceNoTraffic`,
actual 7:36; I forgot that `rate(...[5m]) == 0` cannot be true until the window has fully drained
of the last samples, so the earliest fire is 5 min plus the 3 min `for:`, roughly 8. **Blast
radius: badly wrong.** I predicted two or three alerts. There were **thirteen, on ten services**.

## What the shape at minute twelve shows

| service | error ratio | p95 | req/s before → during |
|---|---:|---:|---|
| `product-catalog` | — | — | 5.03 → **0.000** — the target, frozen |
| `frontend` | 0.00% | **15000** (off scale) | 11.31 → **2.31** — hung on the target, throughput collapsed |
| `frontend-proxy` | **26.17%** | 15000 | 5.40 → 1.96 — Envoy timing out its upstream |
| `load-generator` | **28.71%** | 15000 | 4.88 → 1.77 — the client's view |
| `checkout` | 0.00% | 3 | 1.78 → **0.058** — starved |
| `currency`, `email`, `payment`, `quote`, `shipping`, `accounting` | — | — | → **0.000** — starved; every one fired `ServiceNoTraffic` |
| `recommendation` | 100% | 15000 | 0.58 → 0.004 — its one call in five minutes was to the frozen target |
| `cart` | 0.00% | 3 | 3.80 → 1.26 — degraded, not silent |

**Freezing one leaf service took the whole request path down.** Not because anything else broke,
but because `frontend`'s requests to the frozen service hang until they time out, and while they
hang they hold `frontend`'s capacity. Its throughput fell by 80%, and everything behind it —
seven services — went silent for want of calls. **A frozen dependency is a cascading outage, which
is the most realistic failure shape this benchmark has yet produced on either world.**

## Recovery was not clean, and the reason is real

After the unpause, `ServiceNoTraffic` cleared within a minute as traffic resumed — and then a
**second wave** fired: `ServiceHighErrorRate` on `product-catalog`, `checkout`, `frontend` and
`recommendation`, and `ServiceHighLatency` on `checkout` and `recommendation`, from 14:35:02 to
14:37:32. **A thundering herd.** Every request that had been hanging for up to twelve minutes woke
at once against a service that had just resumed, many of them past their client-side deadlines,
and failed. The target itself showed an error-rate alert *after* it was healthy, for about three
minutes. It self-resolved.

**For the injector**: a pause's restore is instantaneous and its recovery is not. A scenario's
recovery clock starts at the unpause and must allow ~6 min before the world is quiet, and the
harness's `confirm_recovery` will see errors on the target during those minutes that are not the
fault.

## What this changes for the remaining attempts

**A3 may be distinct from A2 after all, on (a).** The registration said the two were the pair most
likely to collapse into one class and named (c) as the only likely separator. But A2 produced a
*hang* — accept-and-never-answer — and a network disconnect should produce a *refusal*: no route,
immediate, a fast error at the caller and no capacity collapse behind it. If that is what A3
shows, the two separate on alert shape and on the whole downstream picture, not only on log
lines. That is now the specific thing A3 tests.

**`ServiceNoTraffic` fires about eight minutes after traffic stops, not three.** The `[5m]` rate
has to drain before it reads zero, and then `for: 3m` applies. Every no-traffic scenario's
expected page time is ~8 min, and the pre-registration's "3–5 min" was arithmetic I got wrong.

**The blast radius is the topology.** ADR-0029 §4 measured that the page flattens onto
`frontend`; A2 measured the other half — that a fault on a hub dependency reaches every service
behind the caller, as silence. The catalog will need to expect `ServiceNoTraffic` on services that
have nothing wrong with them.

## Still owed

**A1's dimension (d) read-back failed**, not on the trace but on the query: Jaeger's API at
`localhost:16686` returned a non-JSON body. The port may not be published to the host, or Jaeger
v2's query path differs. Still owed; `docker port jaeger` is the first thing to check. It does not
bear on A2, whose distinctness rests on (a), (b) and (c).

## Timeline

| clock (UTC) | event |
|---|---|
| 14:20:23 | `docker pause product-catalog` |
| 14:24:59 | first alerts: `frontend-proxy` error rate + latency, `load-generator` error rate (+4:36) |
| 14:26:59 | `ServiceHighLatency/frontend` — direct caller (+6:36) |
| 14:27:59 | `ServiceNoTraffic` on eight services including the target (+7:36) — **PAGES** |
| 14:29:59 | `ServiceNoTraffic/fraud-detection` joins; 13 alerts firing |
| 14:32:26 | `docker unpause product-catalog` |
| 14:33:02 | traffic resumes; no-traffic alerts begin clearing |
| 14:35:02 | second wave: error-rate alerts on the target and three others (thundering herd) |
| 14:38:02 | all clear (+5:36) — **REVERTS** |
| 14:42:02 | recovery window ends; 4 min quiet observed |
