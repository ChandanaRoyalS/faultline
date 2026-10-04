# T7.2 - the SREGym run's problem table

Read for [`PREREGISTRATION-T7.2-run.md`](../../../evals/runs/PREREGISTRATION-T7.2-run.md) on
2026-10-02. Everything was read offline from SREGym at `46c853db` (`SREGym-applications` at
`887d093e`), with no cluster touched, no model called and $0 spent.

| file | what it is |
|---|---|
| `problem_table.py.txt` | instantiates every registered problem with a stub kubeconfig (a server at `127.0.0.1:1`) and records its application, its diagnosis and mitigation oracles, and whether it is in SREGym-Lite |
| `problems.csv` | its output: 125 rows. The seven with an `error` are six FleetCast problems whose submodule is unfetched, and `taint_no_toleration_social_network`, which needs a cluster to construct |
| `families.py.txt` | reads each problem's family from the section comments of SREGym's `registry.py` |
| `families.tsv` | its output: 125 rows |
| `eligible_and_draw.py.txt` | the eligible problems (the three applications with a snapshot, less the three SREGym cannot run on kind) and the dev draw, seed `20261002` |
| `eligible.txt` | its printed output: 111 eligible, the three dev problems marked `DEV` |
| `run-table.tsv` | its table: one row per eligible problem, with application, family, split (`dev` or `scored`), SREGym-Lite membership and Q126's flag |

**One thing to know when re-running.** The first run of `problem_table.py` wrote CRLF line
endings (the `csv` module's default). They were converted to LF, and the script was changed to
write LF. Re-run with the changed script, the output was byte-identical to the converted file.

**Addendum 1, 2026-10-03.** The run scaled to the owner's budget:

| file | what it is |
|---|---|
| `scaled_draw.py.txt` | the scaled run's draw: 11 of each application's scored problems, `random.Random(20261003).sample` over the sorted list, from `run-table.tsv` |
| `scaled-sample.tsv` | its output: 33 problems, with family and Q126's flag |

**Addendum 2, 2026-10-03.** The scored run's operation:

| file | what it is |
|---|---|
| `scored_queue.py.txt` | the attempt order: the 33 problems shuffled by `random.Random(20261004)`, two slots each, the first arm alternating by position |
| `scored-queue.tsv` | its output: 66 slots, copied to the VM as `/tmp/scored-queue.tsv`. `pilot_vm.sh`'s `scored`, `batch`, `tally` and `status` stages run it |

**The scored run, 2026-10-03.** Its records, results and analysis:

| file | what it is |
|---|---|
| `analysis.py.txt` | the report's analysis: pass rates and bootstrap intervals, the paired difference, the predictions, the five categories, triage, the tools, cost and time. Standard library, fixed seed |
| `scored/` | the run's evidence and the analysis' output, with its own [README](scored/README.md) |
