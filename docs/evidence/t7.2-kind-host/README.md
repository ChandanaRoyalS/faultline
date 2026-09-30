# T7.2 step 1b: the deployment as a kind host

**The registration is [`PREREGISTRATION-T7.2-1b.md`](../../../evals/runs/PREREGISTRATION-T7.2-1b.md).**
This directory holds what it was written against and the tool it fixes. The scripts are kept byte
for byte as run, with `.txt` appended so the repository's Python linter and formatter leave them
alone. Each output is verbatim (`docs/evidence` is excluded from the formatting hooks).

| file | what it is |
|---|---|
| `vm_baseline.py.txt` → `vm-baseline.txt` | the deployment VM read-only, 2026-09-30 08:51 UTC, before anything of 1b's |
| `kind_measure.py.txt` | 1b's sampler, fixed by the registration and run unchanged in its phases P0, P2 and P3 |
