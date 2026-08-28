# T7.4 — evidence reachability, characterised

T7.1 recorded that six of twelve scenario targets export no runtime metrics, found only because
the uniform re-record asked every target at once, and never characterised. This characterises it.

**Source: the re-recorded bundles, read off disk. The live world was not used.** Every cell below
comes from a committed capture, the committed graph snapshot, or the tool layer's source.
`reachability.py` regenerates the table.

## What each target can produce

`runtime` counts populated series in the bundle's own `metrics/runtime.json`; `logs` counts
non-comment lines in the bundle's own log capture; `span` is whether the target appears with values
in that bundle's `call-rate`/`error-ratio`/`latency-p95`; `graph` is membership of the committed
span-derived graph snapshot.

| scenario | target | runtime series | families / label | span | graph | logs |
|---|---|---:|---|:---:|:---:|---:|
| ad-memory-squeeze | `adservice` | **48** | `process_runtime_jvm_*` · `exported_job` | ✓ | ✓ | 131 |
| cart-bad-image-tag | `cartservice` | **20** | `process_runtime_dotnet_*` · `exported_job` | ✓ | ✓ | 500 |
| cart-dependency-latency | `cartservice` | **20** | `process_runtime_dotnet_*` · `exported_job` | ✓ | ✓ | 500 |
| cart-redis-misconfig | `cartservice` | **20** | `process_runtime_dotnet_*` · `exported_job` | ✓ | ✓ | 500 |
| currency-cpu-throttle | `currencyservice` | **0** | — | ✓ | ✓ | 456 |
| flag-service-crashloop | `featureflagservice` | **0** | — | **✗** | **✗** | 71 |
| frauddetection-memory-squeeze | `frauddetectionservice` | **38** | `process_runtime_jvm_*` · `exported_job` | ✓ | ✓ | 221 |
| product-catalog-flag-failure | `featureflagservice` | **0** | — | **✗** | **✗** | **2** |
| shipping-wrong-image | `shippingservice` | **0** | — | ✓ | ✓ | 287 |
| email-wrong-image | `emailservice` | **0** | — | ✓ | ✓ | 186 |
| productcatalog-dependency-latency | `productcatalogservice` | **0** | — | ✓ | ✓ | **0** |
| recommendation-memory-squeeze | `recommendationservice` | **13** | `runtime_cpython_*`, `system_memory_*` · `exported_job` | ✓ | ✓ | 116 |

Nine distinct targets across twelve bundles. **Four export runtime metrics** — `adservice`,
`cartservice`, `frauddetectionservice`, `recommendationservice` — under `exported_job`, never
`service_name`. `featureflagservice` is absent from spans and from the graph, which
`context/catalog.py`'s `KNOWN_ABSENT` already records with its measurement.

## The reachability question

**"Was this service idle, or absent?"** Two evidence classes can answer it, and two cannot:

- **Runtime metrics — decisive.** An idle process still reports its heap; a dead one reports
  nothing. Available for four targets.
- **Logs — decisive when the service is talkative.** A restarting process repeats itself; a
  never-created one leaves a stream that stops dead. A service that logs nothing in normal
  operation cannot answer either way, because silence during the fault is indistinguishable from
  its silence at rest.
- **Span metrics and traces — cannot answer, by construction.** Their absence is precisely the
  ambiguity being resolved.
- **Change history — cannot answer.** It says what changed, not what is running.

| scenario | classes that can answer | verdict |
|---|---|---|
| ad-memory-squeeze | runtime (48), logs (131) | 2 |
| cart-bad-image-tag | runtime (20), logs (500) | 2 |
| cart-dependency-latency | runtime (20), logs (500) | 2 — question does not arise |
| cart-redis-misconfig | runtime (20), logs (500) | 2 |
| frauddetection-memory-squeeze | runtime (38), logs (221) | 2 |
| recommendation-memory-squeeze | runtime (13), logs (116) | 2 |
| currency-cpu-throttle | logs (456) | 1 |
| shipping-wrong-image | logs (287) | 1 |
| email-wrong-image | logs (186) | 1 |
| flag-service-crashloop | logs (71), weak | 1 |
| **product-catalog-flag-failure** | **none** | **0** |
| **productcatalog-dependency-latency** | **none** | **0** |

**Two scenarios have no class that can answer it.** `product-catalog-flag-failure`'s target emits
2 log lines and no runtime series; `productcatalog-dependency-latency`'s emits **0 log lines** and
no runtime series — ADR-0005 measured `product-catalog-service` at 0 lines/hour and this bundle
confirms it. For both, every question about what the target's process was doing is unanswerable
with the tools the agent holds.

## Where a narrative teaches a check its target cannot support

Named as defects, per the brief. **All four are narrative defects, not scenario defects** — the
scenarios are recordable and their faults are real; what is wrong is that the write-up names a
check the agent cannot perform.

| narrative | the check it names | why it cannot be made |
|---|---|---|
| `cart-dependency-latency` | *"**Running containers.** A container was attached to cart's network namespace that is not part of any service definition"* | **Container inspection is not a tool.** The agent holds exactly four: `promql_query`, `logql_query`, `trace_query`, `change_history` (`tools/tools.py`). ADR-0019 flagged this at design time — *"one narrative class still reasons from evidence no tool can reach"* — and it was never closed. |
| `productcatalog-dependency-latency` | *"**Running containers.** A container was attached to product catalog's network namespace"* | Same, and worse: this target has **zero** other discriminating classes, so nothing else can substitute. |
| `cart-bad-image-tag` | *"**cartservice container state.** There was no container… no exit code and no restart count"* | Same missing tool. **Mitigated**: the narrative's actual decisive evidence is the log stream's shape, which is reachable — 500 lines. The container-state sentence is unreachable framing around reachable evidence. |
| `cart-redis-misconfig` | *"**cartservice container state, and its logs.** The container was restarting repeatedly"* | Same, same mitigation. |

The distinction matters: the two `dependency_latency` narratives put the **decisive** check on a
missing tool, and the two cart narratives put **framing** there while the evidence that decides is
in the logs. The first pair teaches something unperformable; the second pair teaches something
performable, described in terms of something that is not.

## What it implies, at honest weight

### For the corpus

Seven dev narratives are seeded into the retrieval store as past incidents. **Two of them teach
container inspection as a check** (`cart-bad-image-tag`, `cart-redis-misconfig`) and one teaches it
as *the* check (`cart-dependency-latency`). An agent retrieving them learns to reach for a tool
that does not exist. That is a plausible contributor to wasted dispatches, and **it has not been
measured** — no experiment here has isolated retrieval's effect on tool selection.

*Next step:* measure before editing. A pre-registered comparison of dispatch behaviour with and
without those chunks in the corpus, on the dev split. Rewriting the narratives first would change
the corpus and the numbers together and settle nothing.

### For scoring

T4.11 measured a **5/5 stable abstention** on `product-catalog-flag-failure` — the scenario this
table shows has **zero** classes able to answer what its target was doing. The scorer records that
as `unknown`, identically to an abstention produced by an agent that had the evidence and reasoned
poorly. **Those are different failures and the scorer cannot tell them apart**, which T4.11 said in
prose and this table now supports with a per-scenario measurement.

*Next step:* record reachability as a scenario field, not as a scorer change. The scorer should
keep reporting what happened; the *catalog* should carry what was answerable, so a coverage figure
can be read against it. A scorer that decided for itself which abstentions were excusable would be
grading on sympathy — the failure mode ADR-0022 already names for the dispute register.

### For the catalog's growth

PLAN.md's actual T7.1 grows the catalog past 30 with holdout representation for every fault class.
**This table is the pre-recording check that work needs.** Six of twelve existing bundles were
recorded before anyone asked whether their target could produce the evidence their narrative would
go on to cite, and two of them cannot answer the most basic question about their own target.

*Next step:* make reachability a gate on new scenarios rather than a discovery after recording.
Before a scenario is rehearsed, `reachability.py` is run against its target and the answer is
recorded in the scenario YAML; a target with zero discriminating classes is admitted only
deliberately, with the reason written down. That is a T7.1 deliverable and is **not** built here.

## What this does not establish

The table is a census of what each target *can* emit, not of what any agent *did* consult. It does
not show that unreachability caused any particular abstention — T4.11 argued that for one scenario
from its trajectories, and this table is consistent with it, which is weaker than confirmation.
Nothing here was re-run and no figure moves.
