# T7.38 — disqualification criteria for D1, `redis-cart-dependency-latency`

**Written and committed before the world was touched.**

## The candidate

`dependency_latency` · target **`redis-cart`** · `tc netem` egress delay via pumba — the catalog's
existing latency mechanism, pointed at the **datastore** rather than at a service.

**Slot `dependency_latency-3`, dev.** Confirmed free against T7.35's frozen record, not carried
forward from T7.34's audit. The class's holdout slot is taken by `productcatalog-dependency-latency`,
so this is **dev by position and not by choice**.

## Desk checks, done before any world time

**1. Can the mechanism exist? Yes.** The worry was that `redis-cart` is not one of the demo's own
images and may lack `tc` and `NET_ADMIN`. It does not need them: pumba runs `tc` **from a separate
sidecar image** (`--tc-image`) into the target's network namespace, and the injector's own comment
says so — *"the target container needs no network tooling of its own."* `redis-cart` has an `eth0`,
which is the interface the fault names. **No alternative mechanism is needed.**

**2. A premise has already been fixed and is recorded here rather than watched for.** The brief
names redis-cart's T7.19 `noeviction` monotonic-growth pathology. **T7.28 removed it**: the
container now runs `--maxmemory 12mb --maxmemory-policy allkeys-lru`, and it sits at **3.64M of
12M, evicting.** The confounder as described no longer exists. Memory is still watched during the
probe, because delaying a datastore is exactly the sort of thing that could back work up behind it —
and if memory behaviour dominates, **that is a finding and gets recorded as one, not tuned around.**

## Magnitudes, in order

| # | delay | why |
|---|---|---|
| **V1** | **300ms**, jitter 0 | the parameter the existing `cart-dependency-latency` uses, so a null result is about the *target* rather than about the magnitude |
| **V2** | **600ms**, jitter 0 | only if V1 raises `cartservice` p95 but not past the 250ms rule threshold |

**Two magnitudes, then stop.** No third, no switching target.

## Check order — stop at the first failure

### 1. Does the delay reach `cartservice` at all? *(the load-bearing assumption, tested first and cheaply)*

`ad-dependency-latency` died because a leaf has nowhere to put an egress delay. **`redis-cart` is a
leaf too — the deepest thing in the graph — and the entire design rests on the observer being
`cartservice`, which does have spans.** Delaying redis's egress delays its *responses*, so
cartservice's handler should block waiting for them.

**This is checked with a short probe (~4 minutes), before any alert-budget probe**, because it is
the assumption most likely to be wrong and the cheapest to falsify.

> **DISQUALIFY if `cartservice` p95 does not rise measurably above its 1.9ms baseline at V1 or V2.**
> D1 then dies the way `ad-dependency-latency` did, and the discard is recorded with the measurement.

### 2. Does anything alert, and on the right thing?

**Expected: `ServiceHighLatency/cartservice`**, from the committed rule
`histogram_quantile(0.95, …latency_bucket[2m]) > 250` with `for: 3m`. Very likely joined by
`frontend`, `loadgenerator` and `checkoutservice`, because that is exactly what the neighbouring
`cart-dependency-latency` produced: **four `ServiceHighLatency` alerts, onset 230s.**

> **DISQUALIFY if no alert fires within the 900s correlate budget.**
>
> **DISQUALIFY if the page is dominated by errors rather than latency.** If cartservice's redis
> client times out instead of waiting, this is not a `dependency_latency` scenario — the class would
> be wrong and the labelled remediation would not match.

### 3. Reachability under the fault

The target of the *injection* is `redis-cart`, and reachability is derived for the injection target.
**`redis-cart` emits no spans and logs ~72 lines/hour (ADR-0005), which is below `TALKATIVE_LINES`
over a short window**, and it exports no `RUNTIME_FAMILIES`. So `none_can_answer` may well be
**true**, and that would be disqualifying.

> **DISQUALIFY if `none_can_answer` is true.** An excused failure is not a scored one. **Verified
> against the recorder's derived field, not against reasoning** — T7.22 produced a false
> `none_can_answer` once, and T7.36's author-declared `[runtime, logs]` was wrong and had to be
> corrected against the recorder.

This is the criterion D1 is most likely to fail, and it is named here so that failing it is a
result rather than a surprise.

## The discriminating question, decided in advance

**The page is expected to be near-identical to `cart-dependency-latency`'s.** Both delay the same
path; only the end that carries the `tc` rule differs. So the value of D1 rests entirely on what
separates *"cartservice is waiting on its datastore"* from *"cartservice is broken"*.

**Registered expectation: in the recorded bundle, the separator is `change_history` alone** — it
names `redis-cart` as the container that changed, and nothing else in the bundle names `redis-cart`
at all, because it has no spans and no service-level metrics.

**That does not disqualify D1, and it is not to be dressed up as more than it is.** A scenario
answerable by exactly one tool class is a **narrow item, not a bad one**, and it will be labelled as
narrow in CATALOG.md rather than described as though four classes converge on it. What would make it
wider — cartservice's client span to redis carrying the wait, visible to a live `trace_query` — is
**not in the bundle**, because bundles capture metrics and logs and not traces. If that turns out to
be the real separator it will be recorded as a live-query property with that limitation stated.

> **DO NOT DISQUALIFY for narrowness.** Disqualify only on the checks above.

## World protocol

**Through the harness, so the world lock applies (T7.37).** The recorder takes the lock for the
whole session.

**The short probe calls `docker` directly and is therefore outside the lock**, exactly as T7.30's and
T7.36's probes were. Staying single-driver is handled by the operator rather than by the lock: no
harness process is started while a probe is running, the probe reverts its own sidecar before
exiting, and nothing is queued behind it. **This is stated rather than implied, because the lock does
not cover it.**

kafka recycled before recording; `accounting-service` restarted after any kafka cycle (T7.27); world
left healthy.

**The agent is not run against this.** That is a separate task with its own money.
