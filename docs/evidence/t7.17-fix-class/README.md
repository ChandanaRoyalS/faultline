# T7.17 — which fix actually works

Eight attempts against the live world on 2026-08-29, run to the protocol pre-registered in
[`PREREGISTRATION.md`](PREREGISTRATION.md) before any injection. Raw per-attempt records are the
JSON files beside this one.

## The candidates

| id | operation | the class it tests |
|---|---|---|
| **R** | `docker restart cart-service` | `restart` — the ground-truth label |
| **T** | `tc qdisc del dev eth0 root` in the target's netns, container and sidecar untouched | `config_revert` — revert the network configuration that was changed |
| **S** | `docker stop faultline-pumba-…` | control: the injector's own revert path |

## Results — all eight cleared, durably

| attempt | p95 under fault | qdisc under fault | container id changed | qdisc +60s | qdisc +120s | sidecar at +120s | p95 after | durably cleared |
|---|---:|---|---|---|---|---|---:|---|
| **R1** | 670.6ms | `netem` | no | `noqueue` | `noqueue` | Up 4 minutes | 3.8ms | **yes** |
| **R2** | 662.7ms | `netem` | no | `noqueue` | `noqueue` | Up 4 minutes | 4.8ms | **yes** |
| **R3** | 663.8ms | `netem` | no | `noqueue` | `noqueue` | Up 4 minutes | 4.2ms | **yes** |
| **S1** | 660.5ms | `netem` | no | `noqueue` | `noqueue` | absent | 1.9ms | **yes** |
| **S2** | 661.9ms | `netem` | no | `noqueue` | `noqueue` | absent | 1.9ms | **yes** |
| **T1** | 642.0ms | `netem` | no | `noqueue` | `noqueue` | Up 4 minutes | 1.9ms | **yes** |
| **T2** | 659.1ms | `netem` | no | `noqueue` | `noqueue` | Up 4 minutes | 1.9ms | **yes** |
| **T3** | 647.5ms | `netem` | no | `noqueue` | `noqueue` | Up 4 minutes | 1.9ms | **yes** |
**`container id changed` is "no" for R as well, and that is not an error.** `docker restart`
stops and starts the *same* container, so its id is preserved; what is destroyed and rebuilt is
the network namespace, and the netem qdisc lives there. ADR-0007 described this as the fault
going inert "if its target container is **recreated**" — the container is not recreated, and the
distinction matters because it is why a plain restart is enough.

## What it establishes

**Both fixes work, 3/3 each.** The fault is remediable two ways.

**`config_revert` has a concrete meaning here, and the register said it did not.** T deletes the
netem qdisc from cartservice's `eth0`. The container is never restarted, the pumba sidecar is
still `Up` at +120s, and the delay does not come back — pumba applies its rule once and waits out
`--duration` rather than reconciling, so nothing reapplies it. p95 returns to **1.9ms**, the
committed baseline, in all three attempts.

**T is the less disruptive of the two.** It restores p95 to exactly 1.9ms every time, where R
leaves 3.8–4.8ms at the same point — the post-restart warming CATALOG.md already warns about.
A responder who deletes the qdisc fixes the fault without dropping a connection.

**The injector's own revert (S) behaves as documented**, and is the reason it is a control rather
than a candidate: stopping the sidecar is removing an injected component, which is not an action
a responder who does not know about the injection would take.

## Protocol notes, stated rather than buried

**Every attempt ran with the gate RELAXED, not PASS.** `ServiceHighLatency/checkoutservice` —
T7.14's characterised at-rest excursion (ADR-0025) — was firing throughout, for over 90 minutes.
The relaxation is scoped and was written before it was used: proceed only when every refusal is
that excursion on services other than the target, and `cartservice` itself is at baseline. It was,
at 1.9ms before every injection. The refused condition cannot put or remove a qdisc on
cartservice, and this experiment measures a qdisc, not a blast radius.

**Each attempt reverted through the injector and confirmed recovery**: `noqueue` restored, sidecar
absent, `faultline-inject status` clean. The world was left clean.
