# Pre-registration — scoring `payment-telemetry-blackout` and `redis-cart-dependency-latency`

**Written and committed before any run.** No re-runs to improve a number. If the result is bad, the
result is bad.

## What this is

The two most discriminating items in the catalog, both recorded and never scored. Stamp
**`faultline/0.0.1+prompts:1b0e7cbb4c47`**, budget T4.7's (`changes` 8, others 4, 120k tokens, 600s,
2 rounds) — unchanged, so this measures the agent against two new items and nothing else.

**Holdout is not touched.**

## Repeats: three per scenario, six runs total

**Fixed here and not revisited.** One run per scenario cannot separate a capability from a coin
flip, and both items hinge on a single reasoning step — exactly the case where n=1 is worthless.

Three is SPLIT.md's own floor, for its own reason: *"two cannot show a spread"*, measured on
`cart-bad-image-tag` recording 197s and 301s against an unchanged world. T4.10 measured a 2.6×
breadth spread on a single scenario, so two runs agreeing would still not be evidence.

**Cost against that:** T7.29 measured a mean of **$0.546/scenario**, so six runs is **~$3.3 agent +
~$0.25 judge ≈ $3.6**, and roughly **2.1 hours** of world time at ~0.35 h per run including settles.
Six runs at that price is worth it; twelve would not be, because the second three would refine a
figure whose interval is dominated by n rather than by noise.

**Three each, and no more. An outcome of 2/3 does not license a fourth run to break the tie.**

## Predictions

### D5 `payment-telemetry-blackout` — predicted **correct in ≥ 2 of 3** on fault class

**The correct answer is that `paymentservice` is healthy and its trace export is misdirected**
(`bad_config` / `config_revert`). **The plausible wrong answer is that the service is down**
(`bad_deploy` or `resource_exhaustion`, remediation `restart`).

**Predicting from the bundle rather than from authorship**, the evidence is unusually favourable:

- the page is **one alert, `ServiceNoTraffic/paymentservice`**, and **the alerting service is the
  culprit** — so the dispatch that S7 failed to make on `shipping-quote-misconfig` (zero dispatches
  at the failing service) is here the obvious first move rather than a leap;
- the target's own logs are captured and decisive: **328 lines, 111 `Charge request received.`
  spread across every minute the alert was firing**;
- `checkoutservice`'s error ratio is **0.0**, so the callers visibly succeed.

Two independent captured classes therefore contradict "the service is down", and one of them sits
in the file a responder reads first for the alerting service.

> **Falsified if fault class is correct in ≤ 1 of 3.**

**What I expect the failures to look like, if they happen:** `ServiceNoTraffic` is a strong prior for
a dead service, and a run that answers from the page without opening the logs should return
`bad_deploy` or `resource_exhaustion` with remediation `restart`. **If a run returns "down" while
having read the logs, that is the more interesting failure** and is worth more than the count.

### D1 `redis-cart-dependency-latency` — predicted **class ≥ 2 of 3, faulty service ≤ 1 of 3**

Two separable predictions, because the item splits cleanly.

**Fault class is the easy half.** Four `ServiceHighLatency` alerts with a **0.0 error ratio
everywhere** is the signature of waiting rather than failing, and `dependency_latency` is inferable
**without ever naming the culprit**. Predicted **≥ 2 of 3**.

**Faulty service is the hard half, and I predict it mostly fails.** `redis-cart` appears in **no
metric series at all** (measured: zero Prometheus series match `redis`), is **absent from the
dependency graph** (ADR-0017: infrastructure nodes that emit no spans are not in it), and is
reachable only through `change_history`. Naming it requires the agent to ask about a component
nothing in its evidence mentions. Predicted **≤ 1 of 3**.

**Does the agent consult `change_history` unprompted?** Predicted **yes, in at least 2 of 3** — it is
one of four tools and five of nine rehearsed investigations turn on it. **The predicted failure is
not that it skips the tool but that it queries the wrong subject**: `change_history("cartservice")`,
which is the service the evidence points at, returns empty, and empty is a real answer that should
push it onward rather than stop it.

**If it does not consult `change_history` at all**, the expected verdict is `cartservice` as faulty
service with class `dependency_latency` — right shape, wrong culprit — or an abstention on service.

**An abstention is a legitimate outcome under ADR-0022 and is predicted as a real possibility here**,
not offered as a hedge: an agent that localises to cartservice, finds cart healthy, and declines to
name a component it cannot see is behaving correctly under the abstention rule.

## What would count as the scenario being wrong rather than the agent being wrong

**Verified before registering, so this is decidable rather than arguable:** `change_history` resolves
`redis-cart` (`canonical_service('redis-cart')` → `'redis-cart'`, and it is in `SERVICE_CONTAINERS`),
and the change log **holds 4 records for `redis-cart`**. So the culprit is genuinely reachable.

| observation | reading |
|---|---|
| the agent never calls `change_history` for `redis-cart` | **agent finding** — the tool was available, the records exist, and it did not ask |
| it calls `change_history("redis-cart")` and gets `empty` or `error` | **scenario finding** — the item would be unanswerable, and the CATALOG entry must carry it |
| it never learns `redis-cart` exists, having exhausted the evidence | **scenario finding, weaker** — the culprit is undiscoverable from the graph and from metrics, so the item asks for a name the evidence never supplies |
| it names `redis-cart` in any run | the item is answerable; failures elsewhere are agent findings |

**The third row is the one to watch.** D1 was recorded as a *narrow* item, and there is a line
between narrow and unanswerable. The corpus is what may save it: `cart-redis-misconfig` is a dev
scenario whose narrative names `redis-cart`, so the agent can learn the component exists from a
neighbouring incident. **That is not contamination** — D1's own artifacts are excluded by
leave-one-out — but it is the most likely route to a correct answer, and if that is how a correct run
gets there, the writeup should say so rather than crediting inference.

## Protocol

**A sweep of six runs, declaring `--runs-remaining` and decrementing** — 6, 5, 4, 3, 2, 1 — so T7.32's
gate scopes kafka headroom to the work still to come. **This is that gate's first real use, and
whether it behaved as designed is reported either way**, including if it refuses.

World lock through the harness (T7.37). **kafka recycled only if the gate says to**, not
prophylactically. Full protocol per ADR-0022 §3: gate before every injection, judged,
discard-and-continue with every discard recorded and its reason.

Order interleaved — D5, D1, D5, D1, D5, D1 — so a drift in world state over the sweep does not land
entirely on one scenario.

## How it will be reported

**Accuracy and coverage separately. Recall and precision as a pair, never F.** Every figure with its
n. The pre-registration reproduced beside the result so a reader sees what was predicted before it
was known.
