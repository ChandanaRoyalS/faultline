# T7.2 - the scored run

Read for [`PREREGISTRATION-T7.2-run.md`](../../../../evals/runs/PREREGISTRATION-T7.2-run.md),
Addenda 1 and 2, and reported in [`evals/attempts/T7.2-run/RESULT.md`](../../../../evals/attempts/T7.2-run/RESULT.md).

- **Run**: 2026-10-03, 07:54-23:36 UTC, in three sessions on the deployment, at `d46755e`.
- **Every output is as captured**, with the VM's address replaced by `<the VM>`. The key is absent
  from all of them.
- **The archives** this was taken from are kept off the repository:
  - the record archive, the VM's `run-records.tgz` copied to the Mac as `t72-run-records.tgz`,
    sha256 `f783bebc…`;
  - `collect`'s results archive, the VM's `pilot-results.tgz` copied as `t72-run-results.tgz`,
    sha256 `313076b8…`.

| file | what it is |
|---|---|
| `t72-run-bundles.txt`, `-preread.txt`, `-host-on.txt`, `-setup.txt`, `-key.txt` | the set-up, as the re-check's: the bundles built at `d46755e` (source `9141dfe4…`, seed `9a63a87d…`), five free ports, the kill switch on, the rules once, SREGym and four nodes, the bundle served, the key (106 bytes), the judge alias, the sampler |
| `t72-run-session1-check.txt`, `-session2-check.txt` | the checks between sessions: each Faultline record's opening and triage, the world's incidents, restarts and lowest MemAvailable |
| `done.tsv` | one row per slot: slot, problem, arm, status, success, accuracy, start and end |
| `batch-1.log`, `batch-2.log`, `batch-3.log` | each session's batch output: every try, its exit, its result and the tally after it |
| `hold-1.txt`, `hold-2.txt`, `hold-3.txt` | 1c's sampler, one per session, every 30 s. The third was stopped by the close, before its summary |
| `sN-record/` | each Faultline slot's record (33): SREGym's log, Faultline's logs (`attempt.json`, `investigate.log`, the verdict and narrative), and the incident and the trajectory as JSON lines |
| `results/` | SREGym's per-attempt results file for every attempt, 67 in all, in SREGym's own layout. Slot 58's first try is the incomplete one |
| `claudecode-usage.tsv` | Claude Code's token counts per attempt, extracted once from the session logs in `collect`'s archive. The logs are 19 MB and are kept off the repository |
| `analysis-output.txt` | [`../analysis.py.txt`](../analysis.py.txt)'s output, run from this directory's files. Every figure in the result is in it |
| `t72-run-collect.txt`, `-teardown.txt`, `-cleanup.txt`, `-close.txt` | the close: no key in either archive, no world restart, the cluster and images removed, the rules gone, the key shredded, the directory removed with `sudo`, the kill switch off, no incident |

**To re-run the analysis:**

```bash
cd docs/evidence/t7.2-run
python3 analysis.py.txt scored scored/results . > /tmp/out.txt && diff /tmp/out.txt scored/analysis-output.txt
```
