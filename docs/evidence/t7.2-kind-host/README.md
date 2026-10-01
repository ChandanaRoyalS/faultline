# T7.2 step 1b: the deployment as a kind host

**The registration is [`PREREGISTRATION-T7.2-1b.md`](../../../evals/runs/PREREGISTRATION-T7.2-1b.md).**
This directory holds what it was written against and the tool it fixes. The scripts are kept byte
for byte as run, with `.txt` appended so the repository's Python linter and formatter leave them
alone. Each output is verbatim (`docs/evidence` is excluded from the formatting hooks).

| file | what it is |
|---|---|
| `vm_baseline.py.txt` → `vm-baseline.txt` | the deployment VM read-only, 2026-09-30 08:51 UTC, before anything of 1b's |
| `kind_measure.py.txt` | 1b's sampler, fixed by the registration and run unchanged in its phases P0, P2 and P3 |
| `1b-*.txt` | 1b as run on 2026-09-30, one file per step and phase, read in [`RESULT.md`](../../../evals/attempts/T7.2-1b-kind-host/RESULT.md) |

**Two capture lines are edited.** `1b-step4.txt` and `1b-T2.txt` end with the `ssh -t` client's
`Connection to <address> closed.`, and the address is replaced with `<the VM>`, because the
repository does not record the VM's address. No other byte in any capture is changed.

**Step 1c** ([`PREREGISTRATION-T7.2-1c.md`](../../../evals/runs/PREREGISTRATION-T7.2-1c.md)):

| file | what it is |
|---|---|
| `c1_preread.sh.txt` → `1c-preread.txt` | the deployment read-only before 1c's registration, 2026-09-30 11:36 UTC; the Docker Hub reply's `docker-ratelimit-source` line has the VM's address withheld as above. The script's last check (`git status`) never ran: `docker compose exec` read the rest of the script from stdin |
| `kind_measure_1c.py.txt` | 1c's sampler: 1b's with its directory, kubeconfig, reported paths and headers changed, and nothing else |
| `1c-*.txt` (step1 to step7, P0, status) | 1c's attempt 1, 2026-09-30, and the status read of 2026-10-01 06:07 UTC; INCONCLUSIVE, read in the registration's Addendum 1. The VM's address is withheld in `1c-step1-firewall.txt` and `1c-step4.txt`, as above |
| `1c-r1.txt`, `1c-P1.txt`, `1c-step7r.txt`, `1c-step8.txt`, `1c-P2.txt`, `1c-step9-*.txt` | 1c's retry under Addendum 1, 2026-10-01, read in [its RESULT](../../../evals/attempts/T7.2-1c-astronomy-shop/RESULT.md). `1c-step7r.txt` is the deploy's whole log |
| `c1_step8.sh.txt` | step 8's watcher, run on the Mac; the VM's address is withheld in it as in the captures |
| `1c-T1.txt` to `1c-T4.txt`, `1c-P3.txt`, `1c-incidents.txt` | the teardown as first run. T1 killed its own shell (see the RESULT), so `1c-P3.txt` was read with the cluster still up and is **not** the after-teardown reading |
| `1c-T1b.txt`, `1c-T1c.txt`, `1c-P3b.txt` | the teardown finished, and **P3 of record**. The VM's address is withheld in `1c-T2.txt` too |
