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
