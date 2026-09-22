# Pre-registration — T7.0's eight attempts on the v2 world

**Written before any attempt is run. Nothing below is a result.** This fixes, for each candidate
mechanism, what will be done, what will be undone, what counts as *pages*, what counts as
*distinct*, and what the author predicts — so that no outcome can be read to fit a hope.

**Why attempts and not arguments.** The plan's T7.0 names four fault classes and says *"each new
class rehearsed end-to-end before any scenario is authored against it."* ADR-0029 closed all four by
desk assessment; the record admits (PLAN.md, 2026-09-22) that this violated rule 7, which admits a
substitute *only after an attempt has failed*. These are the attempts. The four the plan names are
tried as written, and four mechanisms this world does support are tried beside them.

**Eight, not nine.** Disk fill is both a named class and the substitute mechanism that would
realise it, so it is one attempt serving both lists.

**Cost**: \$0. No model call. The world is already up (`make world-v2-up`, kafka at 1024M). Each
attempt is a few commands, a twelve-minute observation, an undo, and a ten-minute recovery. All
eight fit in an afternoon. Nothing is scored, nothing is recorded as a bundle, and nothing here
moves either stamp.

## What is decided by this document, and what is not

**Decided here**: which of the eight are admissible as fault classes under ADR-0043's rule — class
≡ injector mechanism, subject to the distinctness criterion ADR-0042 pre-registered. The admissible
set becomes `FaultClass`'s new members, in one change, after all eight are run.

**Not decided here**: thresholds, rule changes, the catalog, the split, or anything about T7.2. If
an attempt surfaces a reason to change an alert rule (A5 may), that is a separate decision with its
own registration.

## The protocol, identical for all eight

1. **Pre-state.** `python3 evals/attempts/shape.py` shows no alert firing and the gate's
   world-health checks pass (`gate.read(world='v2')` refuses only for the pipeline, which is not
   running, and for nothing else). If anything is firing, wait for it to clear plus five minutes.
2. **Inject** with the exact commands in the attempt's section. Note the clock.
3. **Observe** for **twelve minutes**: `python3 evals/attempts/watch.py 12`, and at the end
   `python3 evals/attempts/shape.py <target>`. Twelve is the rules' `[5m]` window plus the longest
   `for:` (3m) plus margin; a rule that has not fired by then is not going to.
4. **Revert** with the exact commands. Note the clock.
5. **Recover**: `watch.py 10`. Every alert must clear and the world must be quiet for the last
   five minutes before the next attempt starts. If it does not recover, that is recorded and the
   next attempt does not start until it does.
6. **Record** the transcript of steps 2–5 verbatim under `evals/attempts/<id>/` with a
   `RESULT.md` that fills in the three verdicts below and nothing else.

## Definitions, fixed now

**PAGES** — at least one of the three v2 alert rules (`ServiceHighErrorRate`, `ServiceHighLatency`,
`ServiceNoTraffic`) reaches `firing` within twelve minutes of the injection command, on the target
service or on a service that calls it directly. A `pending` that never fires does not count. An
alert on an unrelated service does not count and is recorded as a finding.

**DISTINCT from class X** — after it pages, at least one of the following differs from what X
produces, *in a dimension the agent's tools expose*: (a) which rules fire on which services;
(b) whether `change_history` records a change at all (compose-override mechanisms leave one;
docker-level mechanisms leave none — and *no change recorded but the world broke* is itself a
distinguishing signal); (c) the target's log signature; (d) what the target's spans look like —
present and erroring, present and slow, or absent. Docker container state (paused, restarting,
disconnected) is **not** agent-visible and may be recorded but may not be relied on for
distinctness. The comparator X is named per attempt below and cannot be changed afterwards.

**REVERTS** — the undo commands succeed, every alert clears within ten minutes, and the world is
quiet for five. A mechanism that pages but does not revert cleanly is recorded as such and is not
admissible until the revert is fixed; T1.4's bar is inject *and* restore.

**ADMISSIBLE** — pages, distinct from its named comparator, reverts, and is not an existing
mechanism by definition (A6 and A7 fail this last test before running, see below).

## The eight

Order is least disruptive first. A1–A4 need no world change. A5 is a flag. A6 and A8 layer a
compose override on one service. A7 needs a local image build. A8 additionally depends on the
kafka tmpfs already in `world-v2.override.yml`.

The v2 triple, used by every compose command below:

```
V2="-f docker-compose.yml -f ../compose/world-v2.override.yml -f ../compose/telemetry-v2.yml"
```

---

### A1 — feature flag: `productCatalogFailure`

*The substitute already proven by hand on 2026-09-22 (200 → 500 → 200 with a control product at
200). Run again under this protocol so every candidate has the same record.*

- **Mechanism**: set a flagd flag's default variant in the bind-mounted JSON; flagd hot-reloads.
- **Target**: `product-catalog`. Callers: `frontend`, `checkout`, `recommendation`.
- **Inject**: `python3 evals/attempts/flag.py productCatalogFailure on`
- **Revert**: `python3 evals/attempts/flag.py productCatalogFailure off`
- **Comparator**: `bad_config` on the same service — a wrong env var also produces errors there.
- **What would distinguish**: (b) — no compose change is recorded; the only change is flagd's
  own reload line in its log. (c) — the error message is the flag's own text, *"Product Catalog
  Fail Feature Flag Enabled"*.
- **Prediction**: PAGES, `ServiceHighErrorRate/product-catalog`, within 6 min. DISTINCT.
  REVERTS. **Admissible.** Confidence high.

### A2 — process freeze: `docker pause`

- **Mechanism**: freeze the target's processes with the cgroup freezer. It stops answering and
  stops emitting spans; nothing is changed on disk or in any config.
- **Target**: `product-catalog`.
- **Inject**: `docker pause product-catalog`
- **Revert**: `docker unpause product-catalog`
- **Comparator**: `bad_deploy` in its crashloop form (`cart-bad-image-tag`'s shape) — a container
  that is restarting also serves nothing.
- **What would distinguish**: (b) — a crashloop leaves a compose change (the image) in
  `change_history`; a pause leaves nothing. (c) — a crashlooping container logs its startup
  failure repeatedly; a paused one logs nothing at all, and its last line is ordinary.
  (d) — both have absent spans.
- **Prediction**: PAGES — `ServiceNoTraffic/product-catalog` at ~3–5 min, and
  `ServiceHighErrorRate` on `frontend` and/or `checkout` as their calls time out. DISTINCT on
  (b) and (c). REVERTS immediately. **Admissible.** Confidence moderate-high; the uncertainty is
  whether the callers error or merely slow.

### A3 — network partition: `docker network disconnect`

- **Mechanism**: detach the target from the compose network. It keeps running and keeps trying;
  nothing can reach it and it can reach nothing — including the collector.
- **Target**: `product-catalog`. Network: `opentelemetry-demo`.
- **Inject**: `docker network disconnect opentelemetry-demo product-catalog`
- **Revert**: `docker network connect opentelemetry-demo product-catalog`
- **Comparator**: **A2**, deliberately — the two are the pair most likely to collapse into one
  class. Secondary comparator `dependency_latency`, which ADR-0029 §5 said a partition's *fix*
  collides with.
- **What would distinguish from A2**: (c) — a disconnected container keeps logging, and what it
  logs is export failures to the collector (*connection refused* / DNS); a paused one is silent.
  From `dependency_latency`: (d) — latency gives slow spans, a partition gives none.
- **Prediction**: PAGES with the same alert shape as A2. DISTINCT from `dependency_latency` on
  (d). **DISTINCT from A2 on (c) only** — and if the agent's `logql_query` window does not show
  those lines, A2 and A3 are **one class** ("unreachable") and this document says so now.
  REVERTS. Confidence moderate.

### A4 — datastore corruption: `docker exec` into `valkey-cart`

- **Mechanism**: overwrite every key in the cart store with bytes the cart service cannot parse.
  The store is reachable and healthy; its contents are wrong. Repeated every five seconds for the
  window because the load generator writes new carts continuously.
- **Target**: `valkey-cart`; the paging service is `cart`. Callers: `frontend`, `checkout`.
- **Inject** (one line; run it, leave it running in a second terminal, it stops after 12 min):
  `for i in $(seq 1 144); do docker exec valkey-cart valkey-cli EVAL "for _,k in ipairs(redis.call('KEYS','*')) do redis.call('SET',k,'t70-corrupt') end return 1" 0 >/dev/null; sleep 5; done`
- **Revert**: let the loop end (or `Ctrl-C` it), then
  `docker exec valkey-cart valkey-cli FLUSHALL` — every corrupted cart is discarded and the load
  generator makes fresh ones.
- **Comparator**: `bad_config` on `cart` — `cart-redis-misconfig` also produced cart errors, by
  pointing cart at the wrong address.
- **What would distinguish**: (c) — a misconfigured cart logs *connection* failures to the store;
  a corrupted store produces *parse* failures (`InvalidProtocolBufferException` or the C# gRPC
  equivalent) with the store reachable. (b) — no change is recorded.
- **Prediction**: PAGES, `ServiceHighErrorRate/cart`, within 6 min — **if** the cart service
  surfaces a parse failure as an error status rather than treating garbage as an empty cart.
  That is the open question and it is why confidence is only moderate. If it does not page, the
  mechanism is recorded as not observable through the rules and is inadmissible. DISTINCT on (c)
  if it pages. REVERTS.

### A5 — cache stampede: `loadGeneratorFloodHomepage`

*The plan's named class, in the only form this world offers: v2's own flood flag.*

- **Mechanism**: a flag makes the load generator flood `/` with a hundred concurrent requests.
- **Target**: `frontend` and everything behind it.
- **Inject**: `python3 evals/attempts/flag.py loadGeneratorFloodHomepage on`
- **Revert**: `python3 evals/attempts/flag.py loadGeneratorFloodHomepage off`
- **Comparator**: none needed for admissibility; the question is whether it pages at all.
- **The secondary question, fixed now so it cannot be invented afterwards**: whether the world
  produces *any* signal a rule could use even if today's three do not — request rate, CPU, p95
  short of the threshold. `shape.py` at minute twelve records it either way. **A "yes" here does
  not make the attempt pass**; it makes adding a saturation rule (Q13) a measured decision to be
  taken separately.
- **Prediction**: DOES NOT PAGE. ADR-0024 measured 50× load for twenty minutes on v1 with all
  three rules blind, and nothing about v2's rules changes the reason — saturation queues rather
  than errors, and latency is measured on completed spans. Confidence high. The `[5m]` windows
  and 25 users do not bear on it. If it pages anyway, that is the more interesting result and the
  reason to have run it.

### A6 — wrong credential ("cert expiry")

*The plan's named class, in the only form this world offers: a wrong database password.*

- **Mechanism**: compose override of `accounting`'s `DB_CONNECTION_STRING`.
  **This is `BadConfigFault`'s mechanism by definition and cannot be a new class.** It is
  attempted because rule 7 requires it and because whether it pages is a real question.
- **Target**: `accounting`.
- **Inject**:
  `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 -f ../evals/attempts/accounting-bad-credential.yml up -d accounting`
- **Revert**:
  `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 up -d accounting`
- **Comparator**: not applicable — same mechanism as `bad_config`.
- **Prediction**: PAGES is a coin flip. `accounting` fails at startup if the connection is opened
  eagerly (then it crashloops and `ServiceNoTraffic` fires), or at first write if lazily —
  and `Consumer.cs` wraps `ProcessMessage` in a catch that logs and continues, in which case the
  span may not carry an error status and **nothing pages**. Whichever happens, the outcome for
  T7.0 is fixed: **inadmissible as a class**, and a `bad_config` scenario for T7.1 if it pages.

### A7 — N+1 regression, as a built image

*The plan's named class, in the only form a code regression can take here: swap the image.*

- **Mechanism**: `BadDeployFault`'s by definition — an image swap — **and cannot be a new
  class.** Attempted because rule 7 requires it and because a latency-shaped bad deploy would be
  new *variety* for the catalog.
- **Target**: `product-catalog`.
- **Build once** (from `world-v2/`):
  `git apply ../evals/attempts/product-catalog-n-plus-one.patch && docker build -f src/product-catalog/Dockerfile -t faultline-attempt/product-catalog:n-plus-one . && git checkout -- src/product-catalog/main.go`
- **Inject**:
  `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 -f ../evals/attempts/product-catalog-n-plus-one.yml up -d product-catalog`
- **Revert**:
  `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 up -d product-catalog`
- **Prediction**: PAGES, `ServiceHighLatency/product-catalog`, within 8 min. Inadmissible as a
  class; a `bad_deploy` scenario for T7.1 with a latency page shape. Confidence high. If it
  errors rather than slows (the 20 MB memory limit is tight), that is recorded and the multiplier
  is not tuned to fix it in this registration.

### A8 — disk fill: kafka's log directory

*The plan's named class, made aimable by the 256 MiB tmpfs `world-v2.override.yml` now gives
kafka's log directory.*

- **Mechanism**: fill the target's only writable data directory to capacity from inside the
  container. New tool (`dd` via `exec`), new surface (storage); matches no existing mechanism.
- **Target**: `kafka`. Paging services: `checkout` (produces orders), `accounting` and
  `fraud-detection` (consume them).
- **Precondition check**: `docker exec kafka df -h /tmp/kraft-combined-logs` shows a 256M tmpfs.
  If it does not, the override did not take and the attempt stops here.
- **Inject**: `docker exec kafka dd if=/dev/zero of=/tmp/kraft-combined-logs/t70-fill bs=1M count=300`
  (it stops early with *No space left on device*; that is the injection succeeding).
- **Revert**: `docker exec kafka rm /tmp/kraft-combined-logs/t70-fill` — and if kafka is
  crashlooping too fast for `exec` to land, the robust revert is
  `cd world-v2 && DEMO_VERSION=2.2.0 docker compose $V2 up -d --force-recreate kafka`, which
  discards the tmpfs. Then `docker restart accounting fraud-detection checkout` (T7.27: consumers
  do not reconnect on their own).
- **Comparator**: `bad_config` on `checkout` (a wrong `KAFKA_ADDR` also stops orders).
- **What would distinguish**: (c) — kafka's own log says *No space left on device* /
  `KafkaStorageException` and halts; a misconfigured checkout logs connection failures while
  kafka is healthy. (b) — no change recorded. (a) — the consumers go silent too, which a
  checkout-side misconfig does not cause.
- **Prediction**: PAGES — `ServiceHighErrorRate/checkout` within 6 min as `PlaceOrder` fails to
  produce, and `ServiceNoTraffic` on `accounting` and `fraud-detection` at ~3–5 min as the
  consumers starve. DISTINCT on (a) and (c). REVERTS via recreate. **Admissible.** Confidence
  moderate-high; the uncertainty is whether checkout treats a failed produce as a request error
  or logs and returns success.

## What the outcomes decide

| admissible set after all eight | `FaultClass` becomes |
|---|---|
| A1 only | 5 classes |
| A1 + any one of A2/A3/A4/A8 | 6 |
| A1 + two | 7 |
| A1 + three | 8 |
| A1 + all four | 9 |
| A2 and A3 both page but do not separate on (c) | they are one class, `unreachable`, and count once |

A6 and A7 cannot add a class under any outcome; they can add scenarios.

**The class list is then changed once**, in a single patch, with both fingerprints recorded — not
per attempt and not before all eight are run.

## What could go wrong, and the answer fixed in advance

- **A recovery does not complete.** The next attempt does not start. If the world cannot be
  brought quiet by the revert plus a recreate of the affected service, `make world-v2-down &&
  make world-v2-up` and the attempt that broke it is recorded as *does not revert*.
- **An attempt pages on an unrelated service.** Recorded as a finding; does not count as PAGES.
- **The observation window is missed** (a poll fails, the terminal is lost). The attempt is
  reverted, recovered, and run again; the first transcript is kept beside the second.
- **A prediction is wrong.** That is what predictions are for. The verdict is whatever the
  definitions above return, and the prediction is left standing beside it.
