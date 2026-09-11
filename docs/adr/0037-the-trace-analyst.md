# ADR-0037 — the trace analyst: Tempo beside Jaeger, the span tree, and the degrading hop

**Status:** accepted, 2026-09-08
**Task:** T6.1 (*"Add Tempo to the telemetry stack and a fourth specialist that finds exemplar
slow/failed traces and identifies the degrading hop in the request path"*), carrying Q27, Q29 and
Q30, with Q26 tested. Pre-registered in `evals/runs/PREREGISTRATION-T6.1.md` before a line changed.

## Context

The pipeline has had a `traces` specialist since T3.x and a `trace_query` tool since T2.6. What it
did not have was the two things the plan's method column names - *"trace-search and span-tree
summarizer tools"* - or the store the plan names, Tempo. `trace_query` searched Jaeger's UI API,
flattened every trace into a list of `(service, operation, started_at, duration, error)` rows with
neither a span's parent nor its start offset, and truncated at 200 spans. Dev sweep 11 said what
that cost in three verdicts: *"traces carried no timestamps or status codes and were truncated at
200 spans, so the slow spans cannot be pinned to the window or tied to specific errored requests"*;
*"no per-span timestamps, so the before/after question is explicitly unresolved"*. The evidence
was in the traces and the shape hid it. On `redis-cart-dependency-latency` the verdict ranked the
right answer second because it could not place the slow hop and, separately, could not name the
node (Q27).

Every one of those is a digest-locked change: Tempo moves `compose_digest` and
`observability_digest`; a different rendering moves `TOOL_BEHAVIOUR_REVISION` and with it
`CAPABILITY_VERSION`; Q29 moves the prompt stamp. `docs/QUEUE.md`'s whole argument is that such
changes land as one deliberate generation change rather than four, and T6.1 is the world move that
makes that possible. This ADR records what was decided in the landing.

## 1. Tempo beside Jaeger, not instead of it

`compose/telemetry.yml` adds `grafana/tempo:2.4.2` as a single binary with local storage
(`compose/tempo.yaml`: OTLP gRPC receiver on 4317, 24 h block retention, usage reporting off, a
400 MB memory limit the way Loki's is set - and, after the idle measurement reached 95 % of it,
50 MiB blocks released two minutes after completion and `GOMEMLIMIT` 320 MiB, so the limit is a
target the runtime aims under rather than a cliff), and `compose/otelcol-extras.yml` adds an `otlp/tempo`
exporter to the demo collector's traces pipeline **beside** the demo's `otlp` (Jaeger) and
`logging` exporters. Grafana gets a Tempo datasource provisioned under the uid `tempo`
(`compose/grafana-tempo-datasource.yml`), the way `loki` is.

**Jaeger stays** for the reason ADR-0026 gives: the world is a pinned clone of somebody else's
compose file, and removing a service from it through an override is not something compose does
cleanly. Jaeger is the demo's own trace UI behind `frontend-proxy`, Caddy still forwards
`/jaeger*` to it in the deployment, and the T5.4/T5.3c/finding-32 failure mode - its search
answering HTTP 500 whole when one span carries a NaN (Q26) - is no longer on the tool's path. Q26 is
therefore *tested*, not fixed: prediction 8 of the pre-registration says what strikes it.

**The collector merges configs by replacing lists**, so the extras file restates the *whole*
traces exporter list, read from `world/src/otelcollector/otelcol-config.yml` at v1.2.1 rather
than assumed. A list naming only `otlp/tempo` would have silently stopped Jaeger receiving anything,
and the deployment's `/jaeger` route would have gone dark without an error anywhere.

The tool's endpoint is `ToolSettings.tempo_url`, which replaces `jaeger_url`; the deployment sets
`FAULTLINE_TOOLS_TEMPO_URL: http://tempo:3200` and `deploy/compose.world.yml` puts `tempo` on the
shared network beside prometheus, loki and frontend-proxy. `tempo` joins
`injector.world.SERVICE_CONTAINERS` and `knowledge/services.yaml` because the drift test reads every
compose file the injector loads and the deploy overlay must name a service the world defines.

## 2. `trace_query` reads Tempo whole-trace, and keeps the newest

Same signature, same read-only surface, same window policy (onset − 30 min to now, widened only by
the planner's bounded `lookback_minutes`). `GET /api/search?q={resource.service.name="X"}` over the
window returns trace summaries; the tool sorts them **newest first**, fetches each by
`GET /api/traces/{id}` and stops when `max_spans` is reached, so truncation drops the oldest traces
whole rather than the tail of a flat list. `max_traces` (default 10) bounds the fetches. Span status
arrives as a name or an OTLP code and is stored as a name. `TraceResult.source` is `"tempo"`, and
`traces` says how many were fetched.

**A store is only as useful as its freshest searchable trace, and the first configuration got that
wrong.** `ingester.max_block_duration` was 5m, and nothing in Tempo is searchable until a block is
cut: measured on 2026-09-09, the newest searchable trace froze at one instant for five minutes and
then jumped to 14s behind, so **at any moment the tool was blind to the last 0-5 minutes** - the
window an investigation asks about. Two dev sweep 12 verdicts reported exactly that (*"every
returned trace predates onset"*) and both were wrong. At 30s the lag is 6-88s with a median around
14s, and memory falls rather than rises. `compose/tempo.yaml` records the measurement. **This is
why a delta measured on the first configuration would have been a measurement of the config**, and
why the sweep was not run on it.

`ALLOWED_PATHS` gains `/api/search` and `/api/traces/` and loses Jaeger's; the read-only guard is
otherwise unchanged. **Every recorded bundle's `traces/` capture stays what it was**: a recording is
not re-sourced, and the thirteen bundles re-record on the new world anyway (§5).

## 3. The span tree, and the degrading hop (Q30)

`faultline.tools.spantree` builds one tree per trace from `parent_span_id`, renders it with each
span's offset from the trace's root, duration, **self-time** (duration less its children's) and
status, and elides beyond `MAX_DEPTH = 6` levels or `MAX_CHILDREN = 8` siblings **with a marker,
never silently**. A span whose parent is not in the trace as fetched is attached under the root and
counted as unattached, because losing spans is the defect this module replaces.

The **degrading hop** is a rule, stated so a narrative can cite it and a reader can check it:

1. If any span carries an error status, the hop ends at the **deepest erroring span** (ties by
   duration). An error deep in the tree is where the failure originated; the errors above it are
   its propagation.
2. Otherwise follow the **critical path** - from the root, always into the longest child - and the
   hop ends at the span on that path with the **largest self-time**: the span that spent the time
   itself rather than waiting on something below it.

Printed as `caller -> callee  Xms, N% of the trace (error|self-time)`. **Deterministic, no model
call** - the plan's word is *summarizer*, and a summariser that asked a model would be a fifth role
wearing a tool's name. When the culprit is a datastore the world does not instrument, the callee is
the *client* span inside the instrumented service - `cartservice/GetCart -> cartservice/HGET` - which
is the closest an instrumented world can point, and is why Q27 lands in the same bump.

**What the rule does not do**: decide the culprit service, rank hypotheses, or read anything but
the spans it is given. Whether a model handed a tree does better than one handed a list is what dev
sweep 12 measures, and the ADR does not pre-empt it.

## 4. Two things that ride in the same bump

**Q27.** `redis-cart` and `kafka` join `KNOWN_ABSENT` in the service catalog with
`GraphPresence.INFRASTRUCTURE` and a reason each, as ADR-0017 Addendum 3 decided when the first
consumer - the culprit-service axis - arrived. A verdict can now name the thing
`redis-cart-dependency-latency` actually broke. `featureflagservice` is deliberately unchanged as the
control (prediction 6); the prompt-side change that would help it, Q28, is Phase 7's.

**Q29.** `Proposal` moves from `REQUESTED` to `REPORTED`: unexpected keys are accepted, recorded on
the PROPOSAL step and the manifest, and `Dispatch` keeps refusing. ADR-0028 Addendum 2 has the
argument. Landing it here rather than alone keeps *"same stamp, different proposal policy"* from
ever existing in the record.

## 5. The ablation switch, and why it is not a flag on the verdict

`faultline-investigate --without traces`, passed through by `faultline-eval` and `faultline-sweep`.
The planner plans and **is not told**; a dispatch to a withheld specialist is recorded on the
trajectory as its own step (`withheld: true`), on the result as `withheld`, and on the verdict
artifact - and **it is not a failed dispatch**. A failed dispatch flags the verdict, T4.2 reports
flagged runs separately, and an arm in which every run is flagged is an arm compared against nothing.
The manifest carries `ablation: ["traces"]` (`[]` for a full run, written rather than omitted) and
`ablation` joins `FINGERPRINT_INPUTS`, so the two arms can never pool and a full run made after the
switch existed never collides with one made before. Refused for a baseline, which dispatches nothing.

This is the mechanism the plan's *"eval accuracy delta measured"* requires. Nothing in the tree
provided it before, which is why the delta had never been measured.

## 6. What it cost

- `compose_digest` and `observability_digest` move: every published figure becomes a figure about
  generation `f5bd108f4f70`, which is what it always was. Thirteen bundles re-record, narratives
  preserved (T7.28's rule), about two hours on the reference platform.
- **No second `TOOL_BEHAVIOUR_REVISION` bump for the block-duration fix**, and the reason is worth
  stating rather than assuming: `CAPTURE_SET` holds metric files and logs and **no bundle holds a
  trace**, so how fresh Tempo's search index is cannot falsify a claim in any narrative. It changes
  what the *agent* sees at runtime, which the sweep measures directly. It does move
  `observability_digest`, because `compose/tempo.yaml` is under it - so the thirteen bundles record
  again, and that is the whole cost.
- `TOOL_BEHAVIOUR_REVISION` 2 → 3, `cap:c4d52d00` → `cap:dd651ccc`. The fifteen narrative stamps
  were **reviewed, not re-stamped**: `docs/design/t6.1-capability-review.md` names the three claim
  shapes the three changes could falsify, the hits, and why each is unaffected.
- `prompts:b6837dd449ca` → `prompts:06f24e827915`, by Q29 alone. **The pre-registration said the
  stamp would stay, and it was wrong**: §2.3 registered a contract change and §2.4 forgot that a
  contract's schema is in the digest. Amended in the build PR before any run; both arms run at the
  new stamp; `tests/test_harness_run.py`'s ledger records it. Until sweep 12, HEAD has no scored
  run and README's table says so.
- Dev sweep 12: about \$45 of model calls and eighteen hours of the Mac, named in the
  pre-registration under rule 8.

## 7. What this does not settle

Whether the tree helps. Prediction 5 says where it should - the two `dependency_latency` scenarios -
and what it means if it does not: *"the span tree is not doing what §2.2 says and T6.1 is not
delivered, whatever the totals say."* This ADR records a design; `SWEEP-<date>-sweep12.md` records
whether it worked.

## Addendum 1 (2026-09-11) — what dev sweep 12 settled, and what §7 got wrong about where to look

§7 said this ADR records a design and `SWEEP-<date>-sweep12.md` records whether it worked.
[`SWEEP-2026-09-11-sweep12.md`](../../evals/runs/SWEEP-2026-09-11-sweep12.md) does. Three things
belong here because they change how §3 should be read.

**The tree helps, and by more than the class axis was expected to show.** With traces, fault class
26 / 27 and culprit service 23 / 30; without, 20 / 27 with seven abstentions and 18 / 34. The
comparison tool reports +20.0 pp on fault class at n = 10, R = 3 — above the 16.2 pp MDE on the point
estimate, with an interval that reaches zero — and the A/A check, running for the first time,
passed with a largest within-arm delta of 10 pp. Prediction 4 (*no detectable class difference*)
failed in the direction the registration called welcome.

**It helps on the hop §3 did not name.** §3's worked example is the datastore client span inside
cartservice, and prediction 5 named the two `dependency_latency` scenarios as where the gap would
be. Neither moved: `cart-dependency-latency` is 3 / 3 in both arms because cartservice's own
histogram shows the fault, and `redis-cart-dependency-latency` is 0 / 3 on service in both because
the nearest instrumented node is cartservice and that is what the rule prints and the verdict names.
The gap is on `shipping-quote-misconfig` (3 / 3 against 0 / 4), `cart-bad-image-tag` (3 / 3 against
1 / 3) and `shipping-wrong-image` (3 / 3 against 2 / 4): deploy and config faults **downstream of
checkout**, where the failing hop is `checkoutservice/PlaceOrder -> shippingservice/GetQuote`
carrying an error status — rule 1, the deepest erroring span — and where, without it, the
synthesizer reads checkout's log trail stopping and names the next hop by position. **The hop that
matters in this world is the erroring one between two instrumented services, not the slow one
inside a single service.** §3's rule was right; §3's example pointed at the wrong scenario class,
and the pre-registration followed it.

**Prediction 5 therefore fails as written**, and its consequence clause says *"T6.1 is not
delivered, whatever the totals say."* The sweep document puts that sentence beside the plan's
deliverable — *"eval accuracy delta measured"* — and recommends *delivered, with the failure
recorded and the reason it was mis-aimed recorded beside it*, on the ground that the mechanism the
clause exists to catch is visible working in the per-run verdicts. That is the owner's reading to
make, and this addendum records that the ADR's author would make it that way.

**Q26 is retired**, as prediction 8 said it would be if it held: zero NaN-shaped failures across the
sweep. **Q27 is landed and is not the fix** for `redis-cart`; prediction 6's own reading — Q28 — applies.
