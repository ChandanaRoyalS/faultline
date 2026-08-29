# Discarded run

**Reason:** operator error — the fault was reverted out from under a live run.

Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason stay in the
results directory, so the number of runs is a fact nobody can hide by tidying.

## What happened

The run started at 20:01:29Z and injected at 20:01:33Z. Its stdout was block-buffered because it
was not attached to a terminal and was started without `-u`, so the log file sat at zero bytes
while the run was healthy and progressing.

I checked whether it was alive with `pgrep -fc "evalharness.run"`. That is not a valid flag
combination on macOS: `pgrep` printed its usage to stderr and exited non-zero, and the `|| echo
"(process not running)"` fallback fired. An empty log plus that line read as a dead process that
had injected and died, leaving an orphaned fault in the world.

**It was not dead.** It was in `wait_for_incident`, waiting for the alert its own injection was
about to produce. I reverted the fault at roughly 20:05Z, about three and a half minutes in.

## Why it is discarded rather than left to finish

Left alone it would have waited out T7.12's scrape budget and recorded a `no-alert` discard —
which would read as a finding about the scenario. It is not: this scenario fired at T+169s when
recorded, and twice more at T+240s when probed. Letting a `no-alert` record stand here would be
precisely the mistake T7.11 documented, where an environmental cause was written into the record
as a fact about the fault.

**Nothing about the scenario is in question.** No verdict, no trajectory, no cost of note — the run
never reached the investigation. It is replaced by a clean run, and both are counted.

## What was changed so it does not recur

Subsequent runs are started with `python -u` so the log reflects progress, and liveness is checked
with `ps -p <pid>` against the pid the harness records in `.faultline/harness.lock` rather than
with a pattern match. The lock file names the pid for exactly this purpose.
