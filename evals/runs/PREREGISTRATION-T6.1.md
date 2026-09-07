# Pre-registration — T6.1, the trace analyst: Tempo, the span tree, and dev sweep 12 at R=3

**Written and committed before any file of the world changes.** This is the first Phase 6 document,
and it registers the largest single change and the largest single spend this project has made, for
the reason `docs/PLAN.md`'s Phase 6 audit gave: T6.1 is a **world move**, and a world move is the
one moment the digest-locked queue can land as one deliberate re-founding instead of four.

---

## 1. What T6.1 is, in the plan's words

Execution plan §9: *"Add Tempo to the telemetry stack and a fourth specialist that finds exemplar
slow/failed traces and identifies the degrading hop in the request path."* How: *"trace-search and
span-tree summarizer tools; evidence model already accommodates the new modality."* Deliverable:
*"trace evidence in investigations; eval accuracy delta measured."*

Proposal, agent architecture: *"Trace analyst — Tempo exemplar traces for slow/failed requests;
identifies which hop in the request path degrades. Tools: trace search, span-tree summarizer."*

**What the tree has** (Phase 6 audit, ~40%): a `trace_query` tool against Jaeger, a `traces`
specialist the planner dispatches, trace citations that deep-link into Grafana. **What it lacks**:
Tempo; a span tree — the tool flattens every trace and prints neither a span's start time nor its
parent, which three sweep-11 verdicts named as the reason they could not place the failing hop;
any identification of the degrading hop; and the delta, which has never been measured because
nothing can run the pipeline without traces.

---

## 2. Scope — one generation change, and everything it carries

### 2.1 The world (moves `compose_digest` and `observability_digest`)

- **`compose/telemetry.yml`**: a `tempo` service (`grafana/tempo`, version pinned, local storage,
  OTLP gRPC receiver, memory limit set the way Loki's is) and a Grafana Tempo datasource
  provisioned from `compose/grafana-tempo-datasource.yml` the way Loki's is.
- **`compose/otelcol-extras.yml`**: an `otlp/tempo` exporter added to the traces pipeline, **beside**
  the demo's existing exporters. The collector merges its two configs by replacing lists, so the
  extras file restates the full traces exporter list; the exact list is read from
  `world/src/otelcollector/otelcol-config.yml` at v1.2.1 when the build PR is written, not assumed.
- **Jaeger stays.** It is the demo's own trace UI behind `frontend-proxy`, and removing a service
  from somebody else's compose file through an override is not a thing compose can do cleanly
  (ADR-0026). The tool stops reading it; the deployment's `/jaeger` route keeps working. Tempo's
  memory is the cost: measured on the Mac before the first recording, against the kafka headroom
  gate that already refuses at 90 %.

### 2.2 The tool (moves `TOOL_BEHAVIOUR_REVISION` → `CAPABILITY_VERSION`)

- **`trace_query` reads Tempo**: `/api/search` over one service and one window, then `/api/traces/{id}`
  for each returned trace. Same signature, same read-only surface, same window policy.
- **The span tree (Q30)**: spans are kept with `parent_span_id` and rendered as a tree per trace,
  with start offset from the trace's root, duration, self-time, status, and service. Fixed depth and
  width caps, newest traces first, the same truncation direction as today.
- **The degrading hop**: for each trace, the deepest span with error status, else the span with the
  largest self-time on the path from root to the slowest leaf, printed as `caller → callee` with its
  share of the trace's duration. **Deterministic, no model call** — a summariser, as the plan says.
- **Q27 lands here**: `redis-cart` and `kafka` join the service catalog as edgeless entries with
  presence and reason recorded, the way `featureflagservice` is (ADR-0017 Addendum 3). Same bump.
- **Q26 is tested, not fixed**: the NaN-valued span that fails Jaeger's JSON marshalling is no longer
  in the tool's path. Prediction 8 asks whether Tempo tolerates it; if it does, Q26 is struck as
  retired by the world move, and if it does not, the collector-side drop lands in the same batch.

### 2.3 The contracts (Q29)

`Proposal` accepts and records unexpected keys, as `Verdict` has since Q25b. Landing it inside a
generation change keeps "same stamp, different proposal policy" from ever existing in the record.

### 2.4 What does not change, registered

- **No prompt changes.** `prompts:b6837dd449ca` stays. The traces specialist reads a differently
  shaped tool result under the same instructions. If the build finds the specialist needs to be told
  about the tree, **this document is amended and re-merged before the first run**, and the stamp
  moves with it — a prompt edited to help the traces arm and left out of the ablation arm would be a
  comparison of two different agents wearing one name.
- **No budget changes.** The same four bounds every published figure carries.
- **No scenario changes.** The catalog's YAML and truths are untouched; only the bundles re-record.
- **No holdout entry.** ADR-0029 blocks entry 4 indefinitely; the three holdout bundles re-record
  because a recording is injection-only and no agent sees one, exactly as T7.28 did.

### 2.5 The ablation switch (harness, no digest)

`faultline-investigate --without traces` and its `faultline-eval` / `faultline-sweep` passthrough:
the planner's dispatch list is filtered before any specialist runs, the omission is recorded in the
manifest (`ablation: ["traces"]`) and joins `FINGERPRINT_INPUTS`, so an ablation run can never share a
configuration with a full run. This is the mechanism the plan's *"eval accuracy delta measured"*
requires and nothing in the tree provides.

---

## 3. The re-record

All thirteen valid bundles are re-recorded on the new world with `evalharness.rehearse`, holdout
included, **narratives preserved** — `incident.md` is corpus material and a recording of what the
fault did to the world, and T7.28 established that a re-record replaces captures, not narratives.
Costs nothing in model calls; about two hours on the reference platform. Every bundle carries the new
`compose_digest`, `observability_digest` and `capability_version`; every previously published figure
becomes a figure about generation `f5bd108f4f70`, which is what it always was.

---

## 4. Dev sweep 12 — the measurement

**Scope, fixed here.** The ten dev scenarios, **R=3**, three arms:

| arm | what | R | cost |
|---|---|---|---|
| **A** | the full pipeline, traces specialist available | 3 | ~\$22 |
| **B** | the ablation: `--without traces`, everything else identical | 3 | ~\$22 |
| **B0.2** | the heuristic baseline | 1 | \$0 |

**Order**: passes alternate arms — A₁, B₁, A₂, B₂, A₃, B₃, then B0.2 — so that any drift in the
world over the day falls on both arms rather than on one. Each pass is one `faultline-sweep`
invocation at the standard bounds; a kafka recycle between passes is the documented remedy and is
recorded as a continuity event, as in sweep 11. **`--only` is not used**: the scope is the whole dev
catalog, and `faultline-sweep`'s catalog form has run under `--list`'s corrected count since T5.6.

**Why R=3, and why now.** Every figure this project has ever published is R=1. Sweep 10 measured a
fixed-stamp disagreement at n=2 by accident; RESULTS.md called the R=3 repeat *"the highest-value
unspent money in this project"*. This sweep is the first that is *about* a comparison — with traces
against without — and a comparison at R=1 against an MDE of ~28 pp cannot resolve anything a reader
would believe. At R=3 the MDE on ten scenarios falls to roughly 16 pp, the variance component exists
for the first time, and **the A/A check (`evalharness.aa`, built, never runnable) runs for the first
time**, on arm A's passes against each other. Rule 8: the cost is named here — **about \$45 in model
calls, plus about \$1 of judge**, and roughly eighteen hours of the Mac's time across two or three
days — and the owner has said the budget is not the constraint. The wall clock is.

**Judge**: `claude-haiku-4-5`, shared lineage, override recorded on every figure, as before.

---

## 5. Predictions

Each with its consequence named, because that is the only reason to write them first.

### 1. The re-record changes nothing a bundle already recorded, except the digests
`seconds_to_alert` on every bundle within the spread T7.28 measured between its two recordings.
**A bundle whose alert timing moves materially is a finding about Tempo's load on the world, not
about the scenario**, and the recording stops until it is understood.

### 2. No run fails for a trace-tool reason
Zero `trace_query` errors across sixty pipeline runs. **One error is a Tempo integration defect and
outranks every other result**; a pattern of them stops the sweep.

### 3. Arm A produces a verdict or abstains on 30 of 30; so does arm B
A no-verdict is a contract or budget failure and is investigated before any number is read.

### 4. Fault class: no detectable difference between arms
Class accuracy, of answered, within the MDE between A and B. **The plan's *"completes the
four-modality story"* is a claim about localisation, not classification**: the class is usually
decided by change history and metrics, and traces were consulted in two of ten rehearsed
investigations (`roles.py`). A detectable class gain for traces would be welcome and is not
predicted; a detectable *loss* would say the tree summary is crowding the synthesizer's context and
the truncation caps need re-reading.

### 5. Culprit service: arm A ≥ arm B, and the gap is on the two `dependency_latency` scenarios
Where traces should matter is *which hop*: `cart-dependency-latency` and
`redis-cart-dependency-latency`. Arm A names the target on those two at least as often as arm B
across three passes, and **strictly more often on at least one of them**. If arm A shows no
advantage on exactly the scenarios whose fault is a slow hop, the span tree is not doing what §2.2
says and T6.1 is not delivered, whatever the totals say.

### 6. Q27 is the direct test, and it has a control
With `redis-cart` in the catalog, **`redis-cart-dependency-latency` names `redis-cart` as culprit in
at least 2 of 3 arm-A runs** (sweep 11: 0 of 1, ranked second). Its control is
`product-catalog-flag-failure`, whose target `featureflagservice` is unchanged by Q27 and whose
prompt-side fix (Q28) is deliberately *not* in this batch: **it keeps missing**, 0 or 1 of 3. If
both move, the change was not Q27; if neither moves, the catalog entry is not enough on its own and
Q28 is what to look at.

### 7. Latency: arm A is slower than arm B, and both fail G6's inherited clause
Median investigation latency A − B between **+15 s and +60 s** — a fourth dispatch costs a model
call — and both medians above 180 s. **Under 180 s on either arm would be the first on this world and
needs an explanation before it is believed**; a gap above 60 s means the tree summary is too large
for its budget.

### 8. Tempo does not fail whole on a NaN span
Zero Tempo search errors of the `unsupported value: NaN` shape across the sweep. **Held → Q26 struck
as retired by the world move. Failed → the collector-side attribute drop lands in this batch before
the sweep continues.**

### 9. The A/A check declares null
Arm A pass 1 against arm A pass 2 under `evalharness.aa`: **not significant** on every axis. A
significant A/A difference on a fixed configuration is the harness measuring itself, and every
figure in this document is then unreadable until the cause is found. This is the one prediction whose
failure invalidates the rest.

### 10. B0.2 is unmoved
2–3 of 10 on fault class, no service named. The baseline reads no traces and no catalog; if it moves,
the world moved under it in a way the recordings should show.

### 11. Cost
Arm A \$19–26, arm B \$15–22 (one fewer dispatch), judge under \$1.50. Above the range on either arm
is a finding about the tree summary's token weight, and it joins the cost notes.

---

## 6. What this changes afterwards

`docs/RESULTS.md` gains a generation section for the new world with both arms, the variance
component, and the A/A result; README's table regenerates against the new stamp/world pair and its
prose is re-read against it; `docs/GATES.md`'s G6 note records the measured latency clause; Q26, Q27,
Q29 and Q30 are struck as landed or retired, with the figure that did it; ADR-0034 records the design
(Tempo beside Jaeger, the span tree, the degrading-hop rule) and is written with the build, not
after it. T6.1's PLAN entry closes on the sweep's document, `SWEEP-<date>-sweep12.md`, written against
this one.

## 7. What this cannot establish

Nothing about holdout generalisation — no holdout figure exists on any current world and this
sweep does not create one. Nothing at the per-class level: ten scenarios across four classes at R=3
is still 0–3 scenarios per class. And nothing about Tempo as a *product* claim: the plan's word is
*"add"*, and what is measured is whether a span tree changes what the agent gets right.
