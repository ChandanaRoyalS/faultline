# RESULT - T7.2 topology item 3: astronomy-shop's graph under SREGym, against v2's

Read against [`PREREGISTRATION-T7.2-graph3.md`](../../runs/PREREGISTRATION-T7.2-graph3.md) and its
Addendum 1.

- **When and how.** Run on 2026-10-01 23:11 to 2026-10-02 01:30 UTC, by the owner from the Mac.
  Every stage was a `g3_vm.sh` stage on the deployment.
- **Captures.** Kept verbatim in [`docs/evidence/t7.2-topology/`](../../../docs/evidence/t7.2-topology/)
  (`g3-*`), with the VM's address withheld.
- **$0.** No model was called, and no key-like variable was in the deploy's environment.

## The answers

**Question 1: DIFFERENT, as registered, by one edge.**

- **What the hour holds.** SREGym's 60-minute reply has **21 of the v2 snapshot's 22**
  cross-service edges, and no edge the snapshot lacks.
- **The edge missing is `load-generator → flagd`.**
- **The four rarest flag reads are all present**, at **5 calls each**, exactly the v2 world's rate.
- **The table allows only those four to be missing**, so any other missing edge reads DIFFERENT.

**The difference does not survive loading.** `load-generator → flagd` is one of
`ARTIFACT_EDGES_V2`, discarded as the synthetic client's. Loaded with v2's rules
(`ServiceGraph.from_snapshot(path=..., world="v2")`), the two replies give **the same 20 edges
over the same 15 services**, checked by comparing `edge_set` and `nodes`.

**By the owner's decision of 2026-10-02**, what follows is the table's:

- `docs/evidence/t7.2-topology/g3-deps-60m.json` is **astronomy-shop's own snapshot of record**;
- loading by application is registered as a build before any scored run (**Q125**);
- the build can rest on the loaded graphs being identical today, but the snapshot stays the one
  measured on SREGym itself.

**Question 2: YES.** SREGym's live graph, read over the 303 s with the fault in, held two edges:
`load-generator → frontend-proxy` (604 calls) and `cart → flagd` (10). It lacked:

- `frontend-proxy → frontend`;
- every edge of the order path: `frontend → checkout`, checkout's six callees, and
  `shipping → quote`;
- every storefront edge.

The clean hour holds all of those. **So a live graph read during this problem would have shown
triage none of the services around the fault.** That was option B's argued cost in the design
note, and it is now measured on one problem.

## The predictions

| prediction | held? |
|---|---|
| Question 1: SAME | **wrong**: `load-generator → flagd` is absent from SREGym's hour |
| the four rare flag reads appear | **held**: 5 calls each, as on v2 |
| the 30-minute reply is a subset of the 60-minute one | **held**: the same 21 edges |
| the cap holds the hour | **held**: 20 of 20 traces held between 62 and 58 minutes back, for frontend-proxy, frontend and checkout |
| Question 2: YES, and more than the order path | **held**: no storefront edge either |
| what remains with the fault in: `load-generator → frontend-proxy`, `load-generator → flagd`, at most a rare flag read | **wrong in one edge each way**: `load-generator → flagd` was absent (it never appears on SREGym), and `cart → flagd` (10 calls) was present, which is not a rare read |
| the deploy takes 5 to 10 minutes; the recovery under 2 | **held**: 5m45s; the rollout finished in about a minute, and the faulted pod was gone within 81 s |
| MemAvailable at or above 5 GiB through the hold | **held**: minimum 5.12, mean 5.56 |
| none of the 35 touched, no world alert, both ports `000` from outside | **held** |
| $0 | **held** |
| (read before registration) the same paths at about 40 % of v2's rate | **wrong**: `frontend-proxy → frontend` ran at 7,141 an hour against v2's 9,881, so about 72 % |

## Step by step

- **Steps 1 to 8** are read in Addendum 1. The gate passed, the deploy exited 0 with
  `Fault injected`, and both ports answered `000` from outside.
- **Step 9, the recovery** (23:52:31-23:52:34).
  - SREGym's two commands ran, and the rollout completed.
  - **The first read did not pass.** The faulted pod was still listed (`0/1 Completed`,
    `None`/`8.8.8.8`) beside the new one.
  - **A read-only re-read at 23:53:55 passed.** The old pod was gone; the one `frontend` pod was
    `ClusterFirst`, with no nameservers, Running and ready; all 29 pods in `astronomy-shop` were
    Running and ready.
  - `resolv.conf` stayed unreadable: the image has neither `cat` nor `node` on its PATH. By
    Addendum 1 the pod spec decided, as it does for SREGym's own check.
- **Step 10, the hold** (23:55:01-01:05:12). 141 samples:
  - MemAvailable 5.12-6.02 GiB;
  - load1 at most 3.25, memory PSI at most 0.02, CPU PSI at most 4.77;
  - no world alert, and none of the 35 restarted or stopped.

  The capture ran at 01:05:07, 72 minutes after the recovery.
- **Teardown** (01:22-01:24):
  - SREGym's port-forward was listed and killed (no pattern matched its own shell), and 8000 and
    9954 were closed;
  - the cluster, the `kind` network and the node image were removed;
  - the rules and inotify were put back; `~/t7.2-1c`, `~/cache_dir`, `~/.kube` and the Helm
    homes are all absent;
  - the kill switch is off and `git status` empty;
  - no incident opened in the 3 hours to 01:23.
- **P3** (01:25-01:30). MemAvailable 11.55-11.68 GiB, 35 of 38 running, no restart, no alert, no
  tools. Both scripts were deleted from `/tmp`.

## Found on the way

- **`accounting` was OOM-killed on a loop under SREGym.**
  - **The count.** 7 restarts by 01:22. The last ended `OOMKilled`, exit 137, at 01:19:10,
    against a **120 Mi** limit. It had 0 restarts at 23:53.
  - **This is with SREGym's own fix in.** The image is the nightly SREGym pins as the fix for
    opentelemetry-demo#2876.
  - **The node flag.** `kind-worker3`'s OOM flag went from False to True over the hold, which is
    consistent with this. Which node ran `accounting` was not read.
  - **No edge depends on it.** `accounting` has no edge in either graph, so neither question
    depends on it.
  - **It is a fault already present before any problem is injected.** Queued as **Q126** for
    scoping step 6.
- **The chart's own `jaeger` pod survived SREGym's cleanup**, because SREGym deletes by a label
  this chart does not set. Its service names were still redirected, so it received nothing.
  SREGym's Jaeger also lists itself as `jaeger-all-in-one` among the services, which adds no
  edge.
- **SREGym's Jaeger counts no self-edges** (Jaeger v1), where v2's counted 16. Self-edges are set
  aside by definition, so this changes neither answer.
- **The sampler's output reached its file in chunks.** Python buffers a redirected `stdout`, and
  for about forty minutes the log looked stalled while the process was alive. Nothing was lost.
  A later sampler should flush each line.
