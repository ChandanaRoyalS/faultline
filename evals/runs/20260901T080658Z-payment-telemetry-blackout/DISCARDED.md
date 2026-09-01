# Discarded run

**Reason:** killed by the operator, mid-settle, to stop a defective driver.

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the results
directory, so the number of runs is a fact nobody can hide by tidying. **Written by hand because
the harness was killed before it could write its own manifest** — which is itself the reason this
file says so explicitly rather than looking like a normal discard.

## What happened

T7.58's driver script ran six `faultline-eval` invocations back to back **with no wait between
them**. That is an operator defect, not an experimental result: `faultline-eval` does not wait for
the world to settle, it *refuses*, so runs 2, 3 and 4 were refused by the baseline gate within four
seconds of each other — the orchestrator's 300 s settle window from run 1's incident had not
elapsed. By run 5 it had, so run 5 passed the gate and **injected** at `2026-09-01T08:07:01Z`.

The driver was killed at approximately `08:08Z`, after the injection and **before the settle window
that precedes the investigation**. The injection was reverted through the injector
(`faultline-inject stop payment-telemetry-blackout`), the override file was removed, and
`injections.json` returned to `active: {}`.

## What it cost, and what it did not

**No agent ran and no money was spent on this run.** The directory holds `inject.txt` and nothing
else: no `investigate.txt`, no trajectory, no verdict. The investigation is gated behind a 300 s
settle that had not elapsed when the process died.

**So this is not a lost observation.** It is a run that never reached the thing being measured. It
is recorded because it injected into the world, and anything that touches the world is a fact about
the record.

## What is a lost observation

`20260901T074946Z-payment-telemetry-blackout` — run 1 — died on an **API 529 `overloaded_error`**
before the investigation started. That one is environmental, and under T7.58's committed
pre-registration it **costs an observation and is not replaced**: *"a run that dies environmentally
reports at the n it achieved."* The `payment-telemetry-blackout` arm is therefore **n = 2**, not
n = 3, and the report says so.

## The fix

The driver now waits out the settle window between runs instead of letting the gate absorb the
sweep. The gate was right every time it refused; the driver was wrong to ask.
