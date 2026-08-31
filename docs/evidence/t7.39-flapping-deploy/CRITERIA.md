# T7.39 — disqualification criteria for D3, `payment-flapping-deploy`

**Written before the world was touched.** In the event the desk checks resolved it and **no world
time was spent at all** — the criteria are recorded here as written, including the ones that were
never reached.

## The candidate as specified

`bad_deploy` · target `paymentservice` · **slot `bad_deploy-4`, dev** (frozen record; the class's
holdout slot `bad_deploy-6` is free but numbered above two free dev slots, so this is dev by
position).

**D3's entire value is that it is deliberately confusable with `resource_exhaustion`** — a container
that keeps dying looks like a container that ran out of memory. That confusability is the item. If
it is not present *in the recorded evidence*, D3 is not a hard item but an **unanswerable** one,
which is disqualifying.

## Desk checks, in order, stop at the first failure

### 1. What is the injector's third shape, exactly, and does it apply here?

> **DISQUALIFY if the shape does not exist or cannot be produced without new injector work that is
> outside "use the documented third shape".**

### 2. Does anything alert, and which alert?

Confirm against the committed rules before any long probe. A flapping service could produce caller
errors, `ServiceNoTraffic`, or both, and the page differs sharply between them.

> **DISQUALIFY if nothing can alert** — the `flag-service-crashloop` outcome.

### 3. Is it distinct from the two `bad_deploy` scenarios already recorded?

Read both recorded pages **before probing**. T7.38 ended with two items separated by exactly one
tool class; a third near-duplicate is worse than a gap.

> **DISQUALIFY if the page will look the same as an existing one and nothing in the bundle
> separates them.** The discard is cheap now and expensive after a recording.

### 4. The confusability itself — is flap-vs-OOM visible in the bundle?

Verified, not reasoned:

- is the container's **exit reason** visible to any tool class?
- do **memory metrics stay flat**, and are they present at all for this target?
- do **logs** show a clean start-and-die rather than a kill?

> **DISQUALIFY if flap and OOM are indistinguishable in the recorded evidence.** Not a hard item —
> an unanswerable one.

### 5. Remediation identifies the class

ADR-0022 scores class by which remediation works. A rollback to the previous image must fix it, and
a memory-limit raise must not, or the scenario is mislabelled.

### 6. World-settle trap

> **DISQUALIFY if the world will not return to baseline.** Repeated restarts of a checkout-path
> service may pull in the ADR-0025 checkout stall, as T7.30's probe did. A world that will not
> settle is a disqualification, **not something to wait out.**

### 7. Reachability, from the recorder

A service that keeps dying may produce few log lines and no runtime series — exactly the shape that
put D5's criterion 6 at risk.

> **DISQUALIFY if `none_can_answer` is true.**

## Magnitudes, had check 1 passed

| # | flap interval | why |
|---|---|---|
| V1 | whatever the image's own exit produces under `restart: always` | the natural rate |
| V2 | a slowed cycle | only if V1 restarts faster than the 2m rate window can register, the failure mode that killed `cart-memory-squeeze` at 200m |

**Two, then stop.** No third and no switching target — switching target to make a candidate pass is
how three candidates were disqualified in this project after passing a gate on paper.
