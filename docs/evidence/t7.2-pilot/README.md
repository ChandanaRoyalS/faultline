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
| `t72-pilot-podstate-shop.txt` | the shop's pods: `product-catalog`'s loop was at startup only (Addendum 2) |
| `t72-pilot-cluster-reset-1.txt`, `t72-pilot-cluster-reset-2.txt` | a fresh cluster before each of the next two reads |
| `t72-pilot-devread-hotel.txt` | Hotel Reservation: names as spans, alarms on MongoDB, **span metrics for `reservation` alone** (Addendum 2) |
| `t72-pilot-devread-social.txt` | Social Network: names as spans but `nginx-thrift`, no trace, no span metric, no alarm |
| `t72-pilot-teardown-a.txt`, `t72-pilot-host-off-a.txt`, `t72-pilot-cleanup-a.txt`, `t72-pilot-killswitch-off-a.txt`, `t72-pilot-incidents-a.txt` | part A closed: cluster and image removed, rules gone, directory deleted, kill switch off, no incident in two hours |
| `t72-pilot-b-doubled-preread.txt`, `t72-pilot-b-doubled-install.txt`, `t72-pilot-b-doubled-bench-db.txt` | part B's setup run a second time over the first (Addendum 3): the state it found, and migrate missing its database |
| `t72-pilot-b-reset-teardown.txt`, `t72-pilot-b-reset-host-off.txt`, `t72-pilot-b-reset-cleanup.txt` | Addendum 3's reset: database removed, all five ports closed, both copies of the rules gone, directory deleted |
| `t72-pilot-b-preread.txt` to `t72-pilot-b-serve-on.txt` | the clean setup: SREGym pinned, `claudecode` 2.1.288, four nodes, the bundle served; the seed refused for want of the committed acceptances (Addendum 4) |
| `t72-pilot-b-bench-reset.txt`, `t72-pilot-b-bench-db-2.txt` | Addendum 4's recovery: the partial database removed, then the template seeded in full, 334 chunks over 65 documents, body digest `a6de378e3b55`, equal to the working tree's (Addendum 5) |
| `t72-pilot-b-key-judge.txt` | the key on the VM (mode 600, 106 bytes, never printed); the README's dated judge string refused, the alias `anthropic/claude-sonnet-4-6` answered (Addendum 5) |
| `t72-pilot-b-a1-record/` | attempt 1, Faultline on the shop: SREGym's log, Faultline's logs (`attempt.json`, `investigate.log`, the verdict and narrative), and the trajectory, incident and tool calls from the bench database, as JSON lines; the key checked absent (Addendum 6) |
| `t72-pilot-b-a1-hang.txt` | the read after the wait that never returned: SREGym gone, its port-forward left, the shop's and Loki's namespaces deleted, and the results CSV (Addendum 6) |
| `t72-pilot-b-a2-shop-claudecode.txt` | attempt 2, Claude Code on the shop: correct, 89/100, 11.7 min; and the probe beside it: the shipped selector refused and the corrected one accepted, error-status series on three services only, about three minutes of metric history, the change commands' answers up to 328,279 characters (Addendum 7) |
| `t72-pilot-b-a3-hotel-claudecode.txt` | attempt 3, Claude Code on Hotel Reservation: correct, 89/100, 8.5 min (Addendum 7) |
| `t72-pilot-b-a4-hotel-faultline.txt`, `t72-pilot-b-a4-record/` | attempt 4, Faultline on Hotel Reservation: wrong, 22/100; every change query cut at 10,000 characters and `mongodb-rate`'s log query refused; the record from the bench database (Addenda 7, 8) |
| `t72-pilot-b-a5-social-faultline.txt`, `t72-pilot-b-a5-record/` | attempt 5, Faultline on Social Network: wrong, 0/100, *"not established"*; the fallback after six evaluations and 17 minutes; nine of ten tool calls failed (Addendum 8) |
| `t72-pilot-b-a6-social-claudecode.txt` | attempt 6, Claude Code on Social Network: correct, 100/100, 7.4 min (Addendum 8) |
| `t72-pilot-b-results/` | SREGym's `*_ALL_results.csv` for all six attempts, from `collect`'s archive (`sha256 a317da674a341692…`, 2.8 MB, kept off the repository) |
| `t72-pilot-b-collect.txt`, `t72-pilot-b-teardown.txt`, `t72-pilot-b-host-off.txt`, `t72-pilot-b-cleanup.txt`, `t72-pilot-b-cleanup-2.txt`, `t72-pilot-b-killswitch-off.txt`, `t72-pilot-b-incidents.txt` | part B's close: the key in none of the results, the world's restart counts, the cluster and images removed, the rules gone, the key shredded, three root-owned logs removed with `sudo`, the kill switch off, no incident (Addendum 8) |
| `t72-pilot-b-hold.txt` | 1c's sampler over part B, 387 samples 02:16-05:29: MemAvailable at least 4.04 GiB, one alert at 04:34:34-04:36:34 (Addendum 8) |
