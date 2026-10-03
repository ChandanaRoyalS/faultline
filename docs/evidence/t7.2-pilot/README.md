# T7.2 - the dev read and the dev pilot

Registered in [`PREREGISTRATION-T7.2-pilot.md`](../../../evals/runs/PREREGISTRATION-T7.2-pilot.md)
before any stage is run.

| file | what it is |
|---|---|
| `pilot_vm.sh.txt` | every stage of both parts, run one at a time from the Mac. Part A, the dev read: $0 and no key on the VM. Part B, the pilot, which starts only after the dev read's profile patch is merged |

The outputs are added here as `t72-pilot-<stage>.txt` as each stage is run, with the VM's address
withheld. **No output ever holds the key**: no stage prints it, and `collect` checks the results
archive for it.
