# T7.2 - the re-check of the adapter's fixes

Read for [`PREREGISTRATION-T7.2-adapter.md`](../../../evals/runs/PREREGISTRATION-T7.2-adapter.md),
Addendum 4's re-check and Addendum 5. Run 2026-10-03, 06:31-07:20 UTC, on the deployment, at
`6737776`. The box bundle's sha256 is `af70af22…` and the seed bundle's `22c50db8…`. Every output
is as captured, with the VM's address replaced by `<the VM>`. The key is absent from all of them.

| file | what it is |
|---|---|
| `t72-recheck-bundles.txt`, `-preread.txt`, `-host-on.txt`, `-setup.txt`, `-key.txt` | the set-up: five free ports, the kill switch on, the rules once, SREGym and four nodes, the template (334 chunks, 65 documents, `a6de378e3b55`), the bundle served, the key (106 bytes), the judge alias, the sampler |
| `t72-recheck-attempts.txt` | the three attempts' outputs and records' summaries, and the probe beside attempt r1 |
| `t72-recheck-r1-record/`, `-r2-record/`, `-r3-record/` | each attempt's record: SREGym's log, Faultline's logs, the incident and the trajectory as JSON lines |
| `results/` | SREGym's `faultline_ALL_results.csv` for each attempt, from `collect`'s archive (`sha256 9e66a387…`, kept off the repository) |
| `t72-recheck-collect.txt`, `-teardown.txt`, `-cleanup.txt`, `-close.txt` | the close: no key in the archive, no world restart since the pilot, the cluster and images removed, the rules gone, the key shredded, the directory removed with `sudo`, the kill switch off, no incident |
| `t72-recheck-hold.txt` | 1c's sampler, 85 samples 06:36-07:18: MemAvailable at least 5.12 GiB, no alert |
