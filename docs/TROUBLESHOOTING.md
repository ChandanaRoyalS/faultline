# When the harness refuses

**Most refusals here are the system working.** The world this project measures has known
properties that produce failures on first contact, and every one of them is a deliberate check
with a remedy. **If something refuses, read the message — it names the reason and usually the
fix.** This page is what those messages assume you know.

Nothing on this page is a bug in your setup.

---

## "the world is not quiet" / a container is too young

**What you hit:** `make demo` or a scored run refuses shortly after `make world-up`.

**Why:** the baseline gate refuses to inject into a world whose containers have been up less than
**300 seconds**. A container still warming up produces readings that are not a baseline — an early
sample of `cartservice` once produced a 353ms figure that was pure startup and had to be retracted.

**Remedy:** wait five minutes after `make world-up`, then try again.

---

## `checkoutservice` p95 pinned at 15000ms, and `ServiceHighLatency` firing on a world you have not touched

**What you hit:** the gate refuses on a latency excursion you did not cause.

**Why:** **a known pathology of this world, not of your setup.** `checkoutservice` develops a stall
that pins its p95 at ~15000ms. It is documented in
[ADR-0025](adr/0025-the-checkout-tail-and-where-not-to-fix-it.md), which also records why it is not
fixed: the fix belongs in the demo's code, which this project does not patch.

**Remedy, and it is the prescribed one:**

```bash
docker restart checkout-service
```

Then wait for the 300s settle. Latency returns to ~38ms.

---

## "kafka is at N% of its memory limit and would reach ~M% by the end of this run"

**What you hit:** the baseline gate refuses before injecting, naming kafka.

**Why:** kafka's memory grows under load and does not stop. The cause is **emulation, not a leak** —
it runs an amd64 image under Rosetta and the growth is the emulator's JIT translation cache
([ADR-0005](adr/0005-arm64-emulation-and-feature-flag-service.md)'s T7.30 addendum). Measured at
**~150 MB/hour under load** and near-flat at rest. The gate projects that forward over the work you
declared and refuses if the run would finish past the recorder's 90% guard.

**Remedy — and the second command is not optional:**

```bash
docker restart kafka
docker restart accounting-service frauddetection-service checkout-service
```

> **Restarting kafka strands `accountingservice`.** It does not reconnect on its own and will sit
> at 0 req/s until restarted, which then fails a later gate for a reason that looks unrelated.
> `frauddetectionservice` recovers by itself within about three minutes; `accountingservice` does
> not. Restart the consumers every time you cycle kafka.

A restart returns kafka from ~99% to ~26%.

---

## "say whether this is one run or part of a sweep"

**What you hit:** a scored run refuses immediately, having injected nothing.

**Why:** the gate projects kafka's memory over the work still to come, and cannot do that unless
told what the work is. **There is no default**, because defaulting silently to the weaker check is a
guard that protects you only if you remembered it.

**Remedy:** pass `--single-run`, or `--runs-remaining N` counting **down** across a sweep — 6 on the
first of six, 1 on the last.

---

## "another driver holds the world"

**What you hit:** a run refuses naming a pid and what it is doing.

**Why:** one driver of the world at a time. Two harness processes interleaving injections produce
bundles that describe each other's incidents, with nothing in either to show it.

**Remedy:** if the named process is gone, **the lock reclaims itself automatically and records that
it did** — there is no file to delete. If it is alive and wrong, stop it, or re-run with
`--force-lock`, which takes the world and records the takeover in the manifest.

---

## The recorder looks stuck

**It is probably working.** `evalharness.rehearse` **waits** on a dirty baseline rather than
refusing — up to `--baseline-timeout` (default 300s) — and then injects. A message saying the
baseline is not clean means it is alive and holding the world, **not that it has failed.**

**Do not queue a retry against that message.** There is nothing to retry, and a second recorder
firing behind a live one is how a bundle gets recorded against another run's incident.

**Which steps wait, and for how long, is in
[`evals/scenarios/ARTIFACTS.md`](../evals/scenarios/ARTIFACTS.md)** — read it before invoking the
recorder, not after.
