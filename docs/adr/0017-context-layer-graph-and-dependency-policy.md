# ADR-0017: The context layer — service catalog, graph source, and `DependencyPolicy`

- **Status:** accepted
- **Date:** 2026-08-24
- **Task:** T2.4 (context layer), unblocking the seam ADR-0016 left
- **Evidence:** `docs/evidence/t2.4-dependency-graph/` — the measured graph, 24h lookback
  over three injected incidents
- **Design only.** Nothing here is built.

## Context

ADR-0016 shipped `TimeOverlapPolicy` and named its replacement: a `DependencyPolicy` that
joins an episode to an incident when the services are close in the dependency graph. It also
wrote down a prediction — that such a rule would join `emailservice` to the cart incident
through `checkoutservice` — specifically so T2.4 could check it rather than inherit it.

The graph has now been measured. **The prediction holds.** Two other things came out of the
same capture that change what this policy can be asked to do, and both are load-bearing
below: `featureflagservice` has no presence in the graph at all, and the graph cannot
distinguish a synchronous call from an asynchronous one.

## Decision

### The service catalog

**Nodes are the 13 measured services, plus `featureflagservice` carried explicitly as a
known-uninstrumented node.**

The two artifact edges are excluded at load: `loadgenerator -> frontend` is our own synthetic
client and would otherwise make `frontend` the most-depended-on service in the world on
traffic we generate; `frontend-proxy -> jaeger-all-in-one` is the tracing UI being traced.

`featureflagservice` is in the catalog with **zero edges and a recorded reason**, rather than
being absent. The difference matters: absent means *unknown*, and a policy that treats
unknown and no-dependencies alike cannot say why it declined. A node that says "this service
exists, emits no spans (ADR-0006's stub), and can have no edges" lets every consumer
distinguish "not connected" from "not visible", which is the distinction the flag-service
scenarios turn on.

**Identity is `canonical_service` throughout**, as everywhere else in this repo. Not
cosmetic here: the capture contains `frontend-proxy`, which canonicalises to `frontendproxy`,
and `jaeger-all-in-one`, which canonicalises to nothing in `injector.world` and is dropped
with its edge. Graph node names are OTel `service.name` values and agree with compose service
names in 12 of 13 cases; the 13th is exactly the case `canonical_service` exists for.

**Marked for decision: whether infrastructure belongs in the catalog.** `kafka` and
`redis-cart` are absent from the graph for the same reason as the flag service — they emit no
spans — and both are causally central. `kafka` is the broker two of `checkoutservice`'s edges
pass through; `redis-cart` is the datastore in `cart-redis-misconfig`, the catalog's
most-rehearsed scenario, whose root cause is an address pointing at it. Adding them as
edgeless nodes costs nothing and would let a later async annotation hang off `kafka`. Adding
them without a source for their edges risks a catalog that looks more complete than it is.
Not decided here because nothing at T2.4 consumes it; the first consumer should decide.

### The graph source: a committed snapshot, with a drift test

**Commit the snapshot. Do not query Jaeger at runtime.** Three reasons, in order of weight.

**Jaeger here cannot be relied on to answer.** It is all-in-one with in-memory storage, so
the graph exists only as long as the container and only covers spans inside the lookback
window. A restart empties it; a quiet world thins it. A runtime query returns a graph whose
content depends on when it was asked, and a correlation rule that changes its mind because
the tracing backend restarted is worse than one that is merely stale.

**A scored run must not depend on it.** ADR-0008's whole argument is that what a scored run
sees has to be fixed in advance and inspectable. A runtime query during scoring would include
the scenario's own traces in the graph it is scored against — the graph would differ between
two runs of the same scenario, and nothing in the bundle would record which graph was used.

**A snapshot is reviewable.** The artifact-exclusion decision above is a judgement call. In a
committed file it is visible in a diff; in a runtime query it is a filter nobody sees.

**The staleness trade-off is real and the ADR-0014 lesson applies: what pins it, and what
notices drift?** ADR-0014's guard compares content digests of the compose files, and
deliberately does *not* compare `ffs_stub_image_id`, because a field that produces false
positives and cannot produce true ones is worse than absent.

Applied here:

- **What pins it:** the snapshot is committed with its `endTs`, `lookback` and capture time,
  the way a bundle manifest pins a recording.
- **What notices drift:** a test that re-queries Jaeger and fails on a changed edge set,
  **skipping when the world is not running** — exactly the shape of
  `test_the_naming_map_matches_the_compose_files_it_copies`, which guards `injector.world`
  against the same class of drift and skips in CI, which never clones the world.
- **What it must not compare:** `callCount`. It changes on every capture with no change to
  the world, and it is the `ffs_stub_image_id` of this graph — a field that would fire
  constantly and never truthfully. The guard compares the **edge set**, and the edge set only.

### Edge semantics: out of scope for correlation, in scope for blast radius

The graph cannot distinguish sync from async. Measured: `checkoutservice` has four edges at
286 calls each, two synchronous RPCs and two Kafka topics, identical in every field the
dependency API returns. The catalog has already measured that the two kinds behave in
opposite ways under failure — `email-wrong-image` (sync) took `checkoutservice` down;
`frauddetection-memory-squeeze` (async) produced no downstream impact at all.

**The trace graph records call causality, not failure propagation.** An edge says *A's work
reaches B*, never *A waits for B*.

**Which consumers need the distinction is the whole of the decision, and they differ:**

| Consumer | Needs sync/async? | Why |
|---|---|---|
| `DependencyPolicy` (T2.2 correlation) | **No** | It asks whether two services are related at all. Both kinds are relations. Joining an async neighbour into an incident is correct — the fault did reach it. |
| Blast-radius reasoning (T3.1 scores triage on it) | **Yes** | An async downstream failure produces no caller-visible errors. Without the distinction, triage concludes `frauddetectionservice` failing endangers `checkoutservice`, which the bundles measure as false. |
| The synthesizer's causal claims (T3.x) | **Yes** | Same reason, with a citation attached to it. |

**So it is declared out of scope for correlation and in scope for blast-radius reasoning**,
which means T2.4 ships without it and T3.1 cannot.

The three ways to get it, for whoever needs it:

1. **`span.kind` from the underlying traces.** The principled source — `PRODUCER`/`CONSUMER`
   is messaging, `CLIENT`/`SERVER` is synchronous RPC. It is in the spans and absent from the
   dependency API, so it costs a trace query per edge rather than one call. This is the
   option that would still be right on a world nobody has written scenarios for.
2. **Annotation from the catalog's own measured incidents.** We have ground truth about
   failure propagation for exactly the services the catalog has scenarios for — two edges out
   of fifteen. Accurate where it exists, and it cannot be extended without running more
   injections.
3. **Declare it unknown and say so at the point of use**, so a blast-radius claim carries
   "edge kind unknown" rather than an implied "synchronous".

**Marked for decision at T3.1**, which is the first task that needs an answer. Recorded
preference: (1), with (2) as the check on it — the two measured bundles are a test case for
whatever (1) produces, and an implementation that labels the `frauddetection` edge
synchronous is wrong regardless of what its spans appear to say.

**Marked for decision: the same split, for the synthetic-client edge.** *(Added at
implementation — this ADR did not anticipate it.)*

Excluding `loadgenerator -> frontend` removes the **node**, because nodes come from edges and
that was its only one. The service it removes is the one that alerts in almost every captured
incident: `loadgenerator` appears in the alert set of all three cart injections and of
`product-catalog-flag-failure`. So the exclusion that is plainly right for blast radius —
where counting our own synthetic client makes `frontend` the most-depended-on service in the
world — silently costs correlation its most frequent alerting service.

The candidate resolution mirrors the sync/async split above, and for the same reason: one
graph, two consumers, different needs.

| Consumer | Wants the edge? | Why |
|---|---|---|
| `DependencyPolicy` (correlation) | **Yes** | `loadgenerator` really does call `frontend`, and an alert on it really does belong to the incident that is breaking `frontend`. |
| Blast-radius reasoning (T3.1) | **No** | It measures who depends on what, and nobody depends on our load generator. |

**Interim behaviour, as built.** The edge stays excluded everywhere and `loadgenerator` is a
catalog entry with presence `ARTIFACT_ONLY` and its reason recorded — the same treatment
`featureflagservice` gets, applied to a service that is absent for a different reason.
Correlation therefore falls back to time overlap for it, so its alerts still join the right
incident, and the join is recorded as `no_graph_presence` rather than `graph`. Nothing is
lost and nothing is silent; what is missing is the graph having an opinion.

Measured in `tests/test_context.py`, replaying `product-catalog-flag-failure`'s alert set:
all three join rules fire in one incident, and the first two joins come from the fallback
chain because `loadgenerator` opens it. That is the concrete cost, and it is why this is
marked rather than left as an implementation detail.

`frontendproxy` is in the identical position, for the identical reason, and is handled the
same way.

### `DependencyPolicy`

**The rule.** A firing episode joins an incident when its service is within **2 hops**,
undirected, of any service already in that incident. Otherwise it opens a new one.

**Why 2, from the capture rather than from taste.** Over the 13 real nodes and all 78
unordered pairs: 1 hop covers 19%, 2 hops **72%**, 3 hops 97%. One hop fails the measured
`emailservice` case this policy exists to handle — `cartservice` and `emailservice` are two
hops apart. Three hops joins 97% of pairs, which is a rule that never declines, and a policy
that never declines is `TimeOverlapPolicy` with extra machinery.

**And 2 hops is a thin filter, which should be said plainly.** It declines 28% of pairs.
`checkoutservice` has degree 9 and `frontend` degree 5 in a 13-node graph, so nearly every
path runs through a hub. This is a real improvement on time overlap and it is not precision.
Anything reporting on correlation quality should quote the 28%.

**Marked for decision: hub handling.** Treating high-degree nodes as non-transitive — a path
may end at `checkoutservice` but not pass through it — would tighten the rule considerably.
It would also break the `emailservice` case, whose path is exactly `cartservice ->
checkoutservice -> emailservice`. There may be a formulation that keeps one and drops the
other; there is no evidence for one yet, and inventing it here would be picking a mechanism
before there is anything to tune it against.

**A service with no graph presence falls back to time overlap, and the fallback is
recorded.** The flag-service case is worth walking through, because it lands better than it
first appears. `product-catalog-flag-failure` injects on `featureflagservice`, which has no
node — but the alert fires on `productcatalogservice`, which does. The policy therefore
correlates that incident normally, on the service that actually alerted. **The blindness is
about cause attribution, not about correlation:** the graph cannot explain *why* product
catalog is failing, because the service responsible is not in it. That is a limit on the
context handed to an investigation, not on whether the incident is assembled correctly.

The case where correlation itself is blind is a fault on an uninstrumented service that
somehow pages, which today cannot happen — the alert rules are scoped by `service_name` over
`calls_total`, so a service with no spans cannot page at all
(`evals/scenarios/flag-service-crashloop.yaml:3`).

**A missing edge falls back the same way, and this is where silence is dangerous.** If the
graph lacks an edge the policy needs, falling back to time overlap reproduces exactly the
behaviour the graph was meant to improve on — and produces the same answer, so nothing looks
wrong. **Every join therefore records which rule decided it** (`graph`, `time_overlap`, or
`no_graph_presence`), and T4.1 can report the mix. ADR-0008 makes this argument about filter
enforcement in almost these words: a defence that is not observed to fire is a defence nobody
can show is working.

### This is what makes the cap reachable

ADR-0016's consequences record that the concurrency cap is **unreachable by construction**,
not merely untested: `TimeOverlapPolicy` joins any firing episode to any live incident, so at
most one incident is ever non-terminal and nothing in the system can count to two. The cap,
its severity ordering, and its queue are all dead code until something can decline.

`DependencyPolicy` is that something. At a 2-hop radius it declines 28% of service pairs, so
two incidents on unrelated parts of the graph will be live at once and the cap will admit one
and queue the other for the first time.

Two consequences follow, and both should be expected rather than discovered:

- **The cap's placeholders stop being harmless.** `max_concurrent = 3`, the 5-minute settle
  window, the 60-second claim idle timeout and the 5-delivery poison threshold were all
  recorded in ADR-0016 as defaults with reasons and no measurements, safe precisely because
  nothing reached them. Landing this policy reaches them.
- **The eval catalog still cannot exercise any of it.** `require_no_active_faults` means one
  fault at a time, so scored runs will continue to produce one incident and never two. The
  coupling is closed in the product and not in the benchmark, and closing it there needs a
  two-concurrent-fault scenario — which ADR-0016 already marked for T7.1.

## Consequences

**Easier.** The correlation seam ADR-0016 built is filled by a policy grounded in measurement
rather than in intuition, with its own weakness quantified. The catalog gives every consumer
one identity scheme and an explicit answer for the service that has no telemetry.

**Harder.** T3.1 inherits a problem this ADR declines to solve: it needs sync/async and the
graph does not have it. The honest version of blast radius is therefore blocked on a trace
query nobody has written, and the alternative — reasoning from the graph as though every edge
were synchronous — is measurably wrong on two of the fifteen edges we have.

**Join provenance is in-process, and finishing it is scoped to T4.1.** Every correlation
decision records the rule that made it — `graph`, `no_graph_presence`, or
`no_judgeable_candidate` — into a `DecisionLog`, which makes the mix enumerable while the
process lives and not afterwards. **`incidents` has no column for it**, and adding one is an
orchestrator and schema change rather than a context-layer one.

That is a deliberate stopping point rather than an oversight. The consumer of the rule mix is
T4.1's reporting: the question it answers is *how often did the graph actually decide, and
how often did this quietly become time overlap again* — which is a reporting question, asked
of many runs, not something the orchestrator needs in order to run. So the schema change
lands with whoever builds that reporting, and the fact is captured now so it is not
reconstructed later from nothing.

Until then the exposure is exactly one thing: a deployment can fall back on every join and
nobody looking at the database would see it. The log is the reason that is a gap in
reporting rather than a gap in evidence.

**A committed snapshot is a thing that can be wrong.** It is pinned and drift-tested, and the
test skips wherever the world is absent, which is CI. The drift will therefore be caught on a
developer machine with the world up, or not at all until someone looks. That is the same
exposure `injector.world` already carries, accepted for the same reason.

**Marked for decision, collected:** whether infrastructure nodes (`kafka`, `redis-cart`) join
the catalog; how sync/async is obtained, at T3.1; whether hubs should be non-transitive in the
hop rule; and whether the synthetic-client edge should be kept for correlation and excluded
only from blast radius — the last of these added at implementation, since building it is what
showed that dropping the edge drops the node.

**Revisit if:** the world gains instrumentation for the flag service, which would remove the
blindness rather than work around it; Jaeger gains persistent storage, which would weaken the
argument against querying at runtime; or a second target environment appears, where a 13-node
hub-and-spoke graph is not the shape being reasoned about and the 2-hop radius has to be
re-derived rather than inherited.

---

## Addendum — edge kinds measured (2026-08-25)

**The deferred question.** "Edge semantics" above declared sync/async out of scope for
correlation and in scope for blast-radius reasoning, marked the source for decision "at T3.1,
which is the first task that needs an answer", and recorded a preference for `span.kind` from
the underlying traces with the two measured bundles as its check. T3.1 was then blocked on it.

**The method changed, and the preferred source turned out not to exist.** The bundles contain
no trace data at all — `manifest.json`, `incident.md`, `queries.md`, five metric captures and a
log capture, and nothing else. The metric captures are span-derived but every query aggregates
`sum by(service_name)`, so `span.kind` was dropped at capture time and is unrecoverable.

What the bundles do hold is ten incidents in which a named service was broken deliberately, and
that measures **failure propagation itself** rather than the messaging pattern that stands in
for it. Where evidence exists it is therefore stronger than the preferred source would have
been; where no bundle broke a callee there is nothing, and those edges are recorded as
unmeasured rather than inferred.

**The operational definition, because the field name invites the wrong reading.**
`edge_kind` records **measured failure propagation, not messaging mechanism.**

- **`sync`** means *a callee failure was observed to propagate to the caller* — the callee was
  broken or slowed in a recorded bundle and the caller's error ratio or p95 moved with it.
- **`async`** means *a callee failure was observed not to propagate* — the callee was
  demonstrably dead for the whole fault and the caller kept serving without errors.
- **`unmeasured`** means no bundle broke that callee, so nothing was observed either way.

The words are borrowed from the mechanism because they are the words a responder uses, and the
borrowing is where a reader goes wrong: `sync` here is not a claim that the call is a blocking
RPC, and `async` is not a claim that a broker is involved. It happens that the one measured
`async` edge does run over Kafka, which makes the mechanistic reading look confirmed. It is
not the reason the edge is labelled that way.

**`frontend → recommendationservice` is the case that makes the difference concrete.** It is
labelled `sync`, and `recommendation-memory-squeeze`'s narrative opens by saying "frontend does
not fail when recommendations fail" — the frontend renders the page without them. Both are
true. Mechanistically the frontend degrades rather than depending on the callee; measurably its
error ratio went 0.013 → 0.077 when recommendations died, enough that `ServiceHighErrorRate`
fired on `frontend` and `loadgenerator`. Partial propagation is propagation, and for blast
radius the caller belongs in the radius.

A consumer reading `sync` as "blocking RPC" would exclude that edge and under-report the blast
radius by a service the alerting itself named. A consumer reading it as this ADR defines it
gets the right answer. **T3.1 consumes the definition above, not the word.**

**The answer: 9 synchronous, 1 asynchronous, 5 unmeasured**, in
`docs/evidence/t3.1-edge-kinds/README.md` with the figure behind each one. Both cross-checks
reproduce — `checkoutservice → emailservice` is sync (caller error 0 → 0.061 as the callee
died) and `checkoutservice → frauddetectionservice` is async (callee dead for 852s, caller
error 0 → 0). Those two edges are identical in the snapshot, same parent and both at 286 calls,
which is the qualitative finding above now carrying numbers on both sides.

**What this does not change.** Nothing about correlation: `DependencyPolicy` still joins on call
causality, and an async neighbour still belongs in the incident because the fault did reach it.
The kinds land as data on `Edge` for T3.1 to consume.

**What it leaves open.** Five edges — `checkoutservice` to `currencyservice`,
`accountingservice` and `paymentservice`, `frontend → checkoutservice`, and
`shippingservice → quoteservice` — have no bundle that breaks their callee. `accountingservice`
shares a Kafka consumer group with `frauddetectionservice` and is probably async by the same
mechanism; it stays unmeasured, because a structural argument is the kind of inference this
measurement exists to replace. Any blast-radius figure should quote the five.

---

## Addendum 2 — two traversals, and what the hop measurement does and does not justify (2026-08-25)

T3.1's triage is the first consumer of the edge kinds, and building it surfaced a design
decision that was not written down and a fact about this ADR's own measurement that qualifies
it. Both are recorded here rather than in the triage module, because both are about the graph.

### Blast-radius traversal is directed, and the direction follows from the definition

Addendum 1 defines `sync` as **a callee failure was observed to propagate to the caller**. That
is a directed statement, and the traversal was built to match it:

- **Upstream — callee → caller — transitive, to the hop radius.** This is the direction the
  measurement licenses. If `adservice` dies its caller `frontend` is affected, and a caller of
  an affected caller is affected too.
- **Downstream — caller → callee — one step, from alerting services only, and it does not
  compose.** A different claim: not *this was damaged* but *the error might have come from
  here*. `email-wrong-image` is why it exists — `checkoutservice` alerted and `emailservice`,
  the broken one, never alerted at all. It is not followed further because the callee of a
  candidate is a candidate for a fault nobody has evidence of.
- **`async` is crossed in neither direction**, and an `unmeasured` edge is crossed in both and
  reported with the service that arrived through it.

Reading the graph as undirected instead reads the measurement backwards and inflates the
result: from an `adservice` failure it reaches `cartservice`, which merely shares a caller.

### **The hop measurement in this ADR is undirected, and does not justify the directed radius**

This is the caveat that matters, and it is a correction to how the number above should be read.
The 19% / 72% / 97% coverage at 1 / 2 / 3 hops was computed over **undirected** pairs, to decide
how far *correlation* should reach. Triage now uses the same radius for a directed traversal, so
**"the 2-hop radius stands" no longer means what that measurement measured.** Directed 2-hop
coverage over these fifteen edges has not been computed, and the undirected figure is an upper
bound on it, not an estimate of it.

The radius is shared deliberately — an incident and its blast radius disagreeing about how far
apart two services are would make them describe different graphs — but the *evidence* for 2 was
gathered for the other question.

**T4.1's scoring is what will measure directed coverage.** Blast radius is scored against each
bundle's `alerts_over_window` (ADR-0009), so a directed 2-hop traversal that under-reaches shows
up there as a recall miss on services that alerted and were not predicted. That is the number to
look at, and it does not exist yet. If it shows under-reach, the fix is a radius derived from
directed coverage rather than inherited from undirected coverage.

### Two traversal semantics now coexist, and that is intentional

They answer different questions, and the codebase should be read knowing both are present:

| | `DependencyPolicy.match` | `Triage.run` |
|---|---|---|
| question | which past incidents are **near** this one | where failure was **measured** to spread |
| traversal | **undirected**, via `ServiceGraph.hops` | **directed**, per the rules above |
| edge kinds | ignored — an async neighbour is still a relation | honoured — `async` is not crossed |
| radius | `ContextSettings.hop_radius` | the same value |

Correlation ignoring edge kinds is Addendum 1's position unchanged: the fault *did* reach an
async consumer, so joining it to the incident is correct, and only the blast-radius question
needs the distinction.

The two therefore disagree on purpose, and `tests/test_triage.py` pins one case so the
disagreement cannot drift into an accident: for an `adservice` incident, `cartservice` is
**inside** the undirected 2-hop join and **outside** the directed blast radius.
