# T7.17 pre-registration — which fix actually works

**Written and committed before any injection.** Registered so the reading of the outcome is
fixed in advance rather than chosen once the numbers are in.

## The dispute

`CLASS_DISPUTES` has carried two entries on `cart-dependency-latency` since T4.3. Ground truth
says `restart`; the agent has answered `config_revert` under three stamps. ADR-0022 §1.2 decides
the class by **which remediation actually works**, and the register already asserts an answer —
*"pumba binds to the container present, so a restart durably clears the delay while there is no
configuration to revert"* — measured on 2026-08-23 against a world that has since been re-recorded
(T7.1). ADR-0008 withdrew `restart`'s "provisional / least-bad fit" marking on that measurement
without re-testing. This re-establishes it or overturns it.

## The mechanism, as documented

Pumba runs `tc netem` in the target container's network namespace from a privileged sidecar
(`gaiaadm/pumba:0.10.1` driving `gaiadocker/iproute2`). The sidecar holds the rule for its
`--duration` and reverts on SIGTERM. Nothing is written to cart-service: no environment variable,
no compose override, no file. **Whether that means `config_revert` names nothing for this fault is
the question, not the premise.**

## Candidates, one per injection

| id | operation | what it is |
|---|---|---|
| **R** | `docker restart cart-service` | the ground-truth label, `restart` |
| **T** | `tc qdisc del dev eth0 root` in cart-service's netns, container and sidecar both left alone | the concrete candidate for `config_revert`: revert the network configuration that was changed, on the affected service, without restarting it |
| **S** | `docker stop faultline-pumba-cart-dependency-latency` | the injector's own revert path. A **control**, not a candidate class - a responder cannot see the sidecar as configuration - included because it bounds the other two and tests pumba's documented SIGTERM behaviour |

**T is the one that decides the dispute.** If a responder can delete the shaping rule and it stays
deleted, then `config_revert` has a concrete, working meaning here and the register's "there is no
configuration to revert" is false. If pumba reapplies it, the register is right.

## Measured per attempt

Direct observation of the qdisc, not inference from a decaying percentile — `tc qdisc show dev
eth0` reports `noqueue` when clean and `netem delay 300ms` when shaped, instantly and
unambiguously. The 2m rate window makes p95 lag by minutes, which is what made the original
measurement read as a "slow recovery" it was not.

1. qdisc before injection — expect `noqueue`
2. qdisc under fault — expect `netem delay 300.0ms`; p95 under fault
3. apply the remediation
4. qdisc immediately after
5. **qdisc at +60s and +120s** — did it stay cleared, i.e. does pumba reapply?
6. sidecar still running?
7. `faultline-inject status`
8. p95 after the rate window empties

**Durably cleared** := no netem at +60s and +120s, with the sidecar still running (R and T).

**Attempts:** 3 each for R and T, 2 for S.

## Registered interpretation

| outcome | reading |
|---|---|
| R durable, T not | **Label right, agent wrong.** The register is re-established as written. |
| T durable, R not | **Agent right, label wrong.** `restart` is the wrong ground truth. |
| **both durable** | **The fault is remediable both ways.** The register's premise is false, and ADR-0022 §1.2's tiebreak — which assumes one working fix — cannot settle it. Then: is T `config_revert`? and what should the scorer do with a fault that has two working fixes? |
| neither durable | ADR-0007's measurement no longer holds on this world; the fault's remediation is unknown and the label has no support. |

Registered separately, because it is true regardless of outcome: **the agent holds four read-only
tools and executes no remediation.** This measures whether the *label* is true, not whether the
agent could carry the fix out. A finding that `config_revert` works does not mean the agent
demonstrated it.

## Protocol

Baseline gate before every injection; revert and confirm recovery after each; one driver. Attempts
that begin on a refused gate are recorded as refused and repeated, not silently retried - and
`ServiceHighLatency/checkoutservice` was firing when this was written (T7.14's characterised
excursion), so waiting for it is expected and each attempt records the gate it ran under.
