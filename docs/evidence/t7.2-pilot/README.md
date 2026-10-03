# T7.2 - the dev read and the dev pilot

Registered in [`PREREGISTRATION-T7.2-pilot.md`](../../../evals/runs/PREREGISTRATION-T7.2-pilot.md)
before any stage is run.

| file | what it is |
|---|---|
| `pilot_vm.sh.txt` | every stage of both parts, run one at a time from the Mac. Part A, the dev read: $0 and no key on the VM. Part B, the pilot, which starts only after the dev read's profile patch is merged |

The outputs are added here as `t72-pilot-<stage>.txt` as each stage is run, with the VM's address
withheld. **No output ever holds the key**: no stage prints it, and `collect` checks the results
archive for it.

| output | stage |
|---|---|
| `t72-pilot-preread.txt` | before: UTC, all five ports free, 11.6 GB available, no alert, `git status` empty |
| `t72-pilot-killswitch-on.txt` | the kill switch on |
| `t72-pilot-host-on.txt` | docker0 admitted on 8000, 9954, 16443, 55432 and 55480, above the loopback-only drops |
| `t72-pilot-install.txt` | SREGym at the pin, `faultline-agent.patch` applied |
| `t72-pilot-cluster.txt` | four nodes ready |
| `t72-pilot-devread-shop.txt` | the shop: span metrics present under v2's names, no renamed workload, owner and cAdvisor series present, `product-catalog` crash-looping, **Loki absent** (Addendum 1) |
