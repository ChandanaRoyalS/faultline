# ADR-0019: The tool layer — contracts, trust labelling, and where change history comes from

- **Status:** accepted
- **Date:** 2026-08-25
- **Task:** T2.6 (tools), binding on T3.x
- **Design only.** Nothing here is built.

## Context

`ARCHITECTURE.md` names the layer in one row — "PromQL/LogQL/deploy-history tools,
trust-labeled I/O" — and `docs/PLAN.md` carries a **contract not written** marker against it
plus one requirement derived from measurement: the third tool must be **change** history, not
deploy history, because all three `resource_exhaustion` scenarios have a container
resource-limit change as their root cause and nothing else can observe one.

`docs/THREAT-MODEL.md` makes the layer load-bearing for security in two directions: thesis 1
says telemetry is attacker-influenced text flowing into agent context and names T2.6 as where
the defence is built, and thesis 2 says the investigation runtime holds only per-tool
read-only credentials.

What has been missing is a requirements list. There is one, and it has been in the tree since
T1.5.

## The nine investigations are the requirements list

Every rehearsed narrative has a **What was checked** section, written from the responder's
chair, recording what was actually consulted and in what order. **Ten** of them are effectively
ten tool-call traces of successful investigations. Read as requirements rather than as prose:

| Evidence consulted | Narratives | Notes |
|---|---|---|
| **Change history** | **10 of 10** | And in **four** the load-bearing answer is that something did *not* change |
| Error rate / traffic by service | 10 | `ServiceHighErrorRate`-shaped queries |
| Container logs | 7 | In **three** the finding is that the logs say nothing |
| Traces | 2 | `cart-bad-image-tag`, `cart-redis-misconfig` — the first real narrowing in both |
| Running containers | 2 | Both `dependency_latency` narratives |
| Runtime metrics (`exported_job`) | 1 | `recommendation-memory-squeeze` |
| **Corrected at implementation** | | This table first said *nine*; there are ten rehearsed narratives — seven dev and three holdout — and the negatives count was five rather than four. `tests/test_tools.py` now pins both numbers, so the claim is checked rather than asserted. |
| The service's dependencies | 2 | Supplied by the context layer (ADR-0017), not by a tool |

Four things fall out of that table and shape everything below.

**Change history is not the third tool, it is the first.** It appears in every single
investigation, more often than metrics or logs, and it is the *only* evidence type that is
never optional. `CATALOG.md` already says so for the cross-class trap — "what separates them,
and why it is only change history" — and this generalises it.

**A negative is a result.** In four narratives the load-bearing finding is that something did
not change — three say *nothing changed on this service* outright. In three, that the logs are empty. `shipping-wrong-image` turns on **the memory limit
having *not* changed** while the image did. A tool that cannot distinguish *no data* from
*query failed* destroys the evidence in most of the ten investigations, and that distinction is
therefore a contract term rather than an implementation detail.

**The named tool set does not cover the ten.** Traces and running-container state each
appear twice and neither is PromQL, LogQL, or change history. Addressed in §1.

**One narrative class still reasons from evidence no tool can reach.** Both
`dependency_latency` narratives cite *"a container was attached to cart's network namespace
that no service definition creates"*. That is container inspection — the same defect already
found and fixed for the `bad_deploy` narratives and again for the memory narratives, now
present in a third class and never noticed because nobody had written down what the agent can
actually query. Addressed in §3, where it turns out to have a good answer.

## Decision

### 1. The tool set

Three tools, as `ARCHITECTURE.md` names them, with the gaps recorded rather than quietly
absorbed.

**`promql_query(query, start, end, step=15) -> MetricResult`**

Returns the Prometheus `query_range` matrix, typed, with `series: []` a legal and *meaningful*
value. Refuses: any path outside `/api/v1/query` and `/api/v1/query_range`, and any window
longer than retention (6h — `CATALOG.md`, "Prometheus keeps 6 hours"), because a window that
silently extends past retention returns a truthful-looking partial answer.

It must reach `exported_job` series and not only `service_name`. Measured: runtime metrics
carry `exported_job` because Prometheus renamed the exporter's `job` label, and
`recommendation-memory-squeeze`'s investigation turns on their absence. A tool that only
knows the span-metric label set cannot answer the question that narrative asks.

**`logql_query(selector, start, end, limit) -> LogResult`**

Returns lines with timestamps, plus `truncated` and `empty` as distinct typed fields.
Refuses: a window that opens after the incident, because three narratives read logs from
*before* onset and `shipping-wrong-image` says the pre-onset stream "is where it breaks open".
Refuses Loki's push endpoint (§4).

**`change_history(service, since, until) -> ChangeResult`**

Returns change records — see §3, which is the whole of this tool's difficulty. `changes: []`
is the answer in five of nine investigations and must be returned as an empty result with a
confirmed window, never as an error or a silence.

**Two gaps, marked for decision.**

*Traces.* **Decided at implementation (T2.6): yes, four tools.** The measured need stands and
the recorded preference below held — forcing the longer path measures the tool set rather
than the agent. `ARCHITECTURE.md`'s row was updated in the same commit; this ADR is the
decision record. The original reasoning, unchanged:

Two narratives' first real narrowing is a trace query, and `ARCHITECTURE.md` names
no trace tool. Jaeger is already queried by the context layer (ADR-0017), so the cost is low.
The options are a fourth tool (`trace_query`), or accepting that those two investigations take
a longer path through error rates and the dependency graph to the same conclusion. **This is
an `ARCHITECTURE.md` change either way** — the row says three — so it is not settled here.
Recorded preference: add it, because "checkout spans failing on their call to cart" is the
step a human took first in both narratives, and a benchmark that forces a longer path is
measuring the tool set rather than the agent.

*Running containers.* See §3: this turns out to be change history, not a fourth tool.

### `prom.py` is extracted, not imported and not copied

`src/evalharness/prom.py` opens with the argument this section has to answer:

> Extracted from `evalharness.rehearse` when the baseline recorder became a second consumer.
> T4.1's scoring harness will be the third, and all three have to ask the same questions the
> same way — a baseline measured with one query and a scenario scored with a slightly
> different one is not a comparison.

The tool layer is the **fourth** consumer, and the same argument applies to the transport and
not to the queries. The harness's `METRIC_QUERIES` are a fixed capture set; an agent composes
its own PromQL. What must not drift is *how* a query is executed: the endpoints, the `step=15`
default, the whole-second timestamp convention, and `query_range`'s parameter handling.

Three options, and one is ruled out by an existing decision:

| | |
|---|---|
| Tools import `evalharness.prom` | **Ruled out.** ADR-0004: "benchmark infrastructure is not product infrastructure". The product depending on the harness inverts that boundary, and the packageable-container contract would drag the eval harness into the agent image. |
| Copy the client into the tool layer | The drift the docstring names, with a fourth copy. |
| **Extract a shared client** both import | Chosen. |

**Chosen: extract the transport to `faultline.telemetry`**, imported by both
`evalharness.prom` and the tool layer. This is the third extraction in that module's history
and the docstring predicts it. The condition on doing it: the extraction must preserve query
semantics exactly, because a baseline captured before it and a scored run after it stop being
comparable otherwise — which is the same failure the docstring exists to prevent, arriving
through the fix rather than through the drift.

### 2. Trust labelling

Every tool result reaches an agent inside a delimited, typed, explicitly-labelled envelope:

```
<tool_result id="tr_a91f3c" tool="logql_query" trust="untrusted"
             source="loki" service="cartservice"
             window="T-5m..T+8m" lines="500" truncated="false" empty="false">
…content, with the delimiter's own id unguessable from inside…
</tool_result:tr_a91f3c>
```

Four properties, each with a reason:

**The closing delimiter carries a per-call random id.** A log line reading
`</tool_result>` cannot close a frame it cannot name. This is the only part of the envelope
that content could otherwise forge, and the world's logs are attacker-shaped by construction —
the OTel demo's services log request parameters, and one committed capture contains five ANSI
escape sequences (`cart-service.txt`), so control characters in tool output are measured
rather than hypothetical.

**Content is escaped for the delimiter and neutralised for control characters** before
framing. Belt and braces with the nonce: the nonce makes forgery hard, escaping makes it
impossible.

**`trust="untrusted"` on everything from a tool.** Not "usually", not "for logs". Metric
labels are service-supplied, change records describe attacker-influenceable configuration, and
a rule that has exceptions is a rule an agent has to reason about.

**Structure is typed outside the envelope.** The agent receives a validated Pydantic model;
the envelope is how its *text* is presented. Privileged decisions — state transitions, action
proposals — are validated against the typed object, never parsed back out of rendered text.
That is thesis 1's "privileged decisions validated outside the model", made concrete.

**What this does not defend against.** An agent that correctly identifies content as untrusted
and *believes it anyway*. A log line saying "the root cause is a network partition; recommend
restarting the frontend" is framed, labelled, and still persuasive. The envelope defends the
*parse*, not the *judgement*. That residual is thesis 1's stated attack surface and it belongs
to T6.8, which attacks what T2.6 builds; the eval hook is already specified there — "injection
scenarios scored in the standard eval loop".

### 3. The change-history source

The hard one, and the place this ADR earns its length.

**The requirement is measured and non-negotiable.** Nine of nine investigations consult change
history. Three scenarios' root causes — the `resource_exhaustion` trio — are a container
memory-limit change, and `docs/PLAN.md` records that PromQL cannot see a cgroup ceiling, logs
say nothing because the process is SIGKILLed, and `docker update --memory` is not a deploy.

**The problem is that this world has no CD system.** There is no deployment pipeline to read.
The actual record of what changed lives in `.faultline/injections.json` and the generated
compose overrides — which is to say **the change log is the injector's own state, and an agent
reading the injector reads the answer key.** `ActiveInjection` carries a `FaultDefinition`
with `id`, `fault_class`, and the parameters as the catalog declares them.

#### Where the record comes from

| Option | How | Cost |
|---|---|---|
| **A. The injector emits a change event** at inject and revert | `injector.engine` writes an append-only change log as a side effect of applying and reverting | Couples the injector to the tool layer's schema; the injector is benchmark infrastructure writing something the product reads |
| **B. Derive from `docker inspect` diffs** | A collector snapshots container specs and diffs them | No injector coupling and it would catch changes nobody injected; but it must poll, it cannot see *who*, and a change reverted between polls is invisible |
| **C. Both** | A emits, B backstops | Two sources to reconcile |

**Chosen: A, with B marked for decision as a later backstop.**

The deciding argument is that B cannot answer the question five narratives ask. *"Nothing
changed on productcatalogservice"* requires knowing the window was **observed and empty**, and
a poller can only offer "no diff between the snapshots I happened to take". A negative from a
poller is not evidence; a negative from an event log with a confirmed window is. Given that a
negative is the load-bearing finding in four of ten investigations, the source has to be able
to produce a trustworthy one.

The coupling cost is real and is mitigated by the boundary below rather than denied: the
injector writes a **generic change record**, not a fault record, and the tool layer reads it
without knowing an injector exists. The same writer would be a deploy hook in a world that had
deploys.

**This also closes the `dependency_latency` gap.** Both narratives cite a container attached to
the target's network namespace that no service definition creates. Under a change log rather
than a deploy log, *a container being created* **is a change record** — `resource: container`,
`action: created`, with the network-namespace attachment in the diff. The two narratives that
appeared to need container inspection need change history instead, and `docs/PLAN.md`'s
"change-history, not deploy-history" requirement turns out to cover a second class it was not
derived from. That is a prediction this ADR is making and T2.6 should check, in the same spirit
as ADR-0016's `emailservice` prediction.

#### The record shape

```
ChangeRecord:
  id, service, at, actor, resource, action, summary, diff{before, after}
```

`service` is `canonical_service` (ADR-0017). `resource` is one of `image`, `environment`,
`resource_limits`, `container`, `config`. `diff` carries before/after values — measured
requirement: `cart-redis-misconfig`'s investigation turns on reading `REDIS_ADDR` set to
`redis-cart:6380`, so the *value* matters, not just that a variable changed.

#### The leak boundary, and how it is enforced

The narratives already solve this problem for prose. `ARTIFACTS.md` requires writing from the
responder's chair and forbids opening with "the flag service was deployed with a broken image"
because "you have written an answer key, and retrieval will hand it to the agent verbatim".
**The change tool's output surface is under the same discipline**, and for the same reason.

Banned from anything an agent can see: `fault_class`, the scenario id, the injector's fault id,
and the words *inject*, *injected*, *fault*, *faultline*, *chaos*, *scenario*, *rehearsal*.

What replaces them is what a real change record would say:

| The injector knows | The agent sees |
|---|---|
| fault `ad-memory-squeeze`, class `resource_exhaustion`, param `memory=256m` | `service: adservice`, `resource: resource_limits`, `action: updated`, `diff: memory 700M → 256M` |
| fault `cart-redis-misconfig`, class `bad_config` | `service: cartservice`, `resource: environment`, `diff: REDIS_ADDR redis-cart:6379 → redis-cart:6380` |
| pumba sidecar for `cart-dependency-latency` | `resource: container`, `action: created`, attached to `cartservice`'s network namespace |

`actor` is a plausible identity, not `faultline`. **Marked for decision:** whether `actor` is a
fixed synthetic operator, drawn from a small roster to make change-history *ranking* a real
task, or omitted. Omitting it is safest and loses the "who" that the record shape claims to
have; a roster is more realistic and is one more thing that could correlate with the answer.

#### Two boundaries, not one *(added T4.2)*

The list above was written for one surface and then reused for a second. They are different
boundaries, and the first live refusal is what made the difference concrete.

| | **change records** (T2.6, this ADR) | **narratives** (T3.4, ADR-0020 §4) |
|---|---|---|
| who wrote the text | the injector, rendered | the scribe, composing prose |
| can the writer see the answer key? | **yes** - it is derived from it | **no** - only validated findings |
| what a banned word proves | the rendering leaked | nothing, on its own |
| matching | substring | word boundary |
| vocabulary | `BANNED_VOCABULARY` | `HARNESS_VOCABULARY` |

**The decision: terms that reveal the harness are banned in every context; ordinary incident
vocabulary is banned only where its appearance is evidence of leakage.**

Banned everywhere (`HARNESS_VOCABULARY`): the injector's own words - `inject`, `injected`,
`injection`, `injector`, `chaos`, `pumba`, `netem`, `rehearsal`, `rehearse`, `scenario`,
`faultline` - and the four `fault_class` values, which are the answer key itself. Scenario ids
and world-owned tokens keep their existing separate treatment. A narrative never legitimately
needs any of these, so the cost of banning them in prose is nil and the cost of allowing one is
the experiment.

Banned only in machine-derived text (`PROSE_VOCABULARY`): **`fault`**, and it is the only word
that moved. In a change record the string is evidence, because that text is rendered from a
model in which "fault" is the injector's word for what it did. In a narrative it is a responder
writing English.

**Why this was not a judgement call about style.** The guard's first live refusal took run 3's
entire narrative, and the sentence it refused contains no banned word:

> "No prior value was recorded for the Redis address, so it is genuinely unsettled whether 6380
> replaced a working endpoint or was set for the first time over a default."

`default` contains `fault`. So does `faulty`, and `defaulting`. That is exemplary responder
prose about a Redis port, on a scenario whose entire subject is a port that is not the default
one, and the match was a substring one over a list built for a different surface
(`docs/evidence/t4.1-first-scored-run/`).

**Matching differs, and asymmetrically.** Over machine-derived text a substring match is right:
an over-match costs nothing there, and a miss costs the experiment. Over prose it is not, so the
narrative guard matches on boundaries - but the two ends are not symmetric. Nothing may precede
a term, which is what makes `default` safe; ordinary inflections may follow one, because a
strict tail lets `scenarios` and `rehearsed` walk through and both are leaks by any reading.

**What did not change.** `BANNED_VOCABULARY` keeps `fault`, keeps substring matching, and the
change-tool guard is untouched: `KNOWN_LEAKING_FAULTS` still pins exactly
`flag-service-bad-deploy` and `flag-service-crashloop` as the only two faults whose records
leak, and `WORLD_OWNED_TOKENS` still exempts exactly `FAULTLINE_ENABLED_FLAGS`.

**Enforcement is a test, not a review.** `evals/scenarios/` already carries
`test_narratives_do_not_leak_the_answer_key`; the change tool gets the same guard, greping its
**rendered output surface** — not its internal model — for the banned vocabulary, over every
fault in `injector.catalog`. A leak guard that reads the source rather than the output is the
same mistake as a drift guard that compares `callCount`.

**~~Marked for decision:~~ decided at implementation (T2.6): a `change_records` table in the
platform Postgres**, beside incidents, written by the injector through a small emitter
(`injector.changelog`). The product reads a table; the injector's state files stay its own.

The deciding argument was ADR-0004's runtime contract, which requires the agent runtime to be
packageable as a standalone container receiving its endpoints from configuration. A JSONL file
under `.faultline/` would have made change history the one tool that needed Faultline's
filesystem, so the runtime would not have been packageable without it.

The two remaining decisions keep their implemented defaults and stay marked: `actor` is the
fixed synthetic `platform-automation`, and there is no `docker inspect` backstop.

### 4. Credentials

Thesis 2 says the investigation runtime holds only per-tool read-only credentials. Against
this world that phrase needs care, because **Prometheus and Loki have no authentication at
all**, and read-only cannot come from the server:

- `compose/telemetry.yml:69` runs Prometheus with `--web.enable-lifecycle`, so
  `POST /-/reload` is exposed to anything that can reach the port.
- `compose/promtail-config.yml:20` shows Loki's `/loki/api/v1/push` open, by necessity.

So an agent with a raw HTTP client and the endpoint could reload Prometheus's configuration or
write fabricated log lines into the corpus it is investigating. **Read-only is therefore a
property of the tool surface, not of the credential**, and that has to be stated rather than
assumed by anyone reading thesis 2:

1. **The tools expose query paths and no others.** `promql_query` reaches `/api/v1/query` and
   `/api/v1/query_range`; `logql_query` reaches `/loki/api/v1/query_range` and the label
   endpoints. Nothing constructs an arbitrary path from agent input.
2. **No tool takes a URL, a host, or a path from an agent.** Endpoints come from configuration
   (ADR-0004's runtime contract requires exactly this), so an agent cannot redirect a tool at
   an endpoint of its choosing.

   *Corrected at implementation.* The first cut of `promql_query` called a `query_range`
   whose base URL **defaulted** to a module constant, so `ToolSettings.prometheus_url` was
   accepted and ignored. Both values were `http://localhost:9090`, so nothing failed and
   nothing showed — a deployment could have configured an endpoint and been answered by
   whatever was on the local port, which is the runtime contract broken quietly. The fix is
   not to pass the setting: the default is **removed**, so `base` is required and
   keyword-only and there is nothing for any caller to inherit. It was the only implicit
   endpoint in the codebase — every other call site, the eval harness included, already
   passed one explicitly, which is why the harness never had this defect and why the tool
   layer inherited it from the one function that did.
3. **`change_history` is read-only by construction** — the writer is the injector, and the
   tool has no write path to reach.

**Deferred to T6.8, explicitly:** actual credentials on Prometheus and Loki, network policy
restricting who can reach them, and egress restriction. All three are listed there already.
Deferring is defensible only because the world is a local benchmark; a deployed instance with
an unauthenticated Prometheus reachable from the agent container is a finding, not a
configuration.

### 5. What T3.x consumes

Enough contract that T3.x can be designed against this ADR without reading tool source.

**Calling convention.** Every tool is a typed function: a Pydantic request in, a Pydantic
result out, no exceptions across the boundary. Failure is a value — `ToolResult.error` — not a
raised exception, because an agent has to be able to reason about a failed query, and an
exception unwinds past the point where that reasoning would happen.

**Every result carries, without exception:**

| Field | Why |
|---|---|
| `id` | Stable handle. `ARCHITECTURE.md` requires the synthesizer produce a **cited, citation-validated** RCA, so every claim needs something to cite that a validator can resolve. |
| `trust` | Always `untrusted` from a tool (§2). |
| `source`, `window` | What was asked, so a negative result names the window it is negative over. |
| `empty` vs `error` | **Distinct fields.** The negatives above are load-bearing; conflating them destroys the evidence. |
| `truncated` | A capped result that looks complete is the `logql_query` failure mode — the committed captures hit a 500-line cap and one narrative's argument depends on knowing that. |

**What T3.x may assume.** Tools are idempotent and side-effect free; repeated identical calls
return the same result for the same window (retention permitting). Tools do not retry
internally past one attempt — an agent deciding whether to retry is a planning decision.

**What T3.x may not assume.** That a tool set covers the investigation: the traces gap above is
real until it is decided. That a window is available: 6h retention is hard, and a tool refusing
an out-of-retention window is the correct behaviour, not an error to work around.

## Consequences

**Easier.** T3.x has a contract to design against, and the requirements came from nine
investigations that actually succeeded rather than from imagining what an agent might want.
The leak discipline the narratives already enforce extends to the tool surface with the same
mechanism, so there is one idea to understand rather than two.

**Harder.** The injector now writes something the product reads, which is a boundary ADR-0004
would rather not cross. It is crossed deliberately and narrowly: a generic change record, no
injector vocabulary, a guard on the output surface. Anyone extending it should be reminded
that the reason for the discipline is that the injector holds the answer key.

**A third narrative class was found reasoning from unreachable evidence**, and this ADR does
not fix it. Both `dependency_latency` narratives cite running-container inspection. If §3's
prediction holds and a created container is a change record, the narratives should be rewritten
against change history the way the memory and `bad_deploy` narratives already were — and if it
does not hold, they need the same treatment for a different reason. **Owned by T2.6**, since
building change history is what will settle it.

**Two catalog faults cannot be rendered as a non-leaking change record — found by the guard,
at implementation.** `flag-service-bad-deploy` and `flag-service-crashloop` deploy stub images
whose tags name what they do: `faultline/ffs-stub:broken` and `faultline/ffs-stub:crashloop`.
An honest image-change record has to name the image deployed, and `crashloop` is the answer
outright. They are pinned rather than exempted — the guard asserts these and only these leak,
so a third is a failure — and they are tolerable only because both scenarios are **blocked**
and can never be rehearsed. Renaming the tags edits `compose/ffs-stub/`, which feeds
`ffs_stub_source_digest`, so it joins the digest-locked queue for T7.1. **Landed at T7.1** - the
variants are now `ffs-stub:1/:2/:3` over `server.py`/`server_v2.py`/`server_v3.py`. Recorded here
because T7.45's sweep found this sentence still reading as pending.

A third token is exempted rather than pinned: `FAULTLINE_ENABLED_FLAGS`, the variable
`product-catalog-flag-failure` changes. It leaks this harness's existence and not the answer,
and it is likewise digest-locked. One line, visible, with the reason beside it.

**Container inspection: closed at T7.6, and the answer was already built.** This ADR flagged
that both `dependency_latency` narratives reason from evidence no tool can reach - *"a container
was attached to cart's network namespace that no service definition creates"* - and owned the
question to T2.6, "since building change history is what will settle it". It did settle it, and
nobody went back to check: the emitted change record for a `dependency_latency` fault reads
**`container created: traffic-shaping container attached to cart-service's network namespace`**
with `None -> eth0 delay=300ms jitter=0ms`, filed under the target service's own name. That is the
narratives' decisive finding, verbatim, through `change_history`.

**So no tool is needed and none was added.** T7.5 recorded these two narratives as possibly
unfixable without a new tool and flagged `productcatalog-dependency-latency` as having no
substitute evidence at all; **both of those flags were wrong**, because T7.5 reasoned from its
reachability table, which answers "was the target idle or absent" and not "what changed beneath
it". The two questions have different answers and the table was only ever built for the first.

What was actually wrong was the narratives: written at T1.5, before a change log existed, they
assert *"what changed on cartservice: nothing"* - which is now false against the log that has
existed since T2.6. T7.6 rewrote both to source the finding where it lives.

**Marked for decision, collected:** whether `docker inspect` diffing backstops the emitted
change log, and whether `actor` is synthetic, a roster, or absent. *(The trace tool and the
change-log location were decided at implementation — see above.)*

**Revisit if:** the world gains a real deployment mechanism, which would replace the emitted
log with an ordinary source and remove the leak boundary entirely; T7.2's SREGym interface
turns out to supply its own tool set, which ADR-0004 already warns is provisional; or the
trace gap is decided against, in which case two scenarios are measuring a tool set rather than
an agent and the catalog should say so.

## Addendum (T3.2b, 2026-09-02) — the window policy is the tool layer's

The plan's T3.2b, *Temporal scoping*, says: *"every tool derives its default window from alert
onset (onset − 30 min → now), the change analyst alone widens its lookback (onset − 24 h, because
causes precede symptoms), and the planner may widen a window per hypothesis — all enforced at
the tool layer, never left to agent discretion."* Deliverable: *"Tool-enforced window policy +
per-query window logging."*

What existed: `default_window(anchor, before=10, after=5)` in `agents/roles.py`, applied to
every specialist alike, and a single six-hour span check in `Tools._check_window` that
`change_history` did not call. The window was chosen in the agent layer, the same for all
four specialists, and the change analyst looked back fifteen minutes for causes that precede
symptoms by hours. The Phase 3 audit recorded this as *partial*.

### What is built

`faultline/tools/window.py` holds one `WindowPolicy`, constructed by `Tools` from the same
`ToolSettings` as the tools it bounds and exposed as `Tools.window_policy`. It does two things.
It **derives**: `for_specialist(name, anchor, now)` returns `onset − 30 min → now` for
`metrics`, `logs` and `traces`, and `onset − 24 h → now` for `changes`, with the rule that
produced it (`default` / `change_lookback`) and whether it was clipped. It **enforces**:
`refusal(tool, start, end)` is what `_check_window` now asks, for all four tools including
`change_history`, and a refusal carries a narrowing hint that names the policy's default.

`now` is the moment the investigation began, fixed once in `Investigation.run` and recorded as
the trajectory's `started_at`, so every dispatch of one investigation shares one end and a replay
with the same two instants asks the same windows. The agent layer no longer computes a window:
`Specialist.window(anchor, now)` asks the policy, and `default_window` is gone.

**Per-query window logging**, both places it is useful: a `faultline.tools.window` log record
for every tool call — tool, subject, start, end, span, refused — and on the trajectory step's
`tool_call.request`, beside the window: `window_rule`, `lookback_seconds`, `clipped`.

### Two ceilings, one derived

The telemetry ceiling stays at six hours. **Its justification changed and the number did not**:
`max_window_seconds` was documented as Prometheus retention (*"Prometheus keeps 6 hours"*), T7.1
raised retention to 15 days and the docstring was never updated. It is now a policy bound —
twelve times the default lookback — and the plan needs *some* bound because it says unbounded
requests are refused. The change tool cannot share it, since a 24-hour change window is the
policy; its ceiling is the change lookback plus the telemetry bound (30 h), derived rather than a
second invented number.

A window that *would* exceed its ceiling because the investigation began long after onset is
**clipped and labelled**, not refused: a policy whose own default is refused by its own check is
a contradiction. Live investigations start minutes after onset and never clip; the tests in this
repository run with a historical anchor and the real clock, and every one of them now records
`clipped: true` instead of reading nothing and calling it evidence.

### What this does and does not move

Nothing frozen. The lookbacks are settings (`FAULTLINE_TOOLS_DEFAULT_LOOKBACK_SECONDS`,
`FAULTLINE_TOOLS_CHANGE_LOOKBACK_SECONDS`), not prompt text, so `prompts_hash()` is unchanged;
the window travels to the specialist in the user message, which was already true.
`capability.tool_surface()` reads the public *functions* of `Tools`, and the policy is an
attribute, so `CAPABILITY_VERSION` is unchanged — checked before and after: `cap:9c416e0a` both
times. `TOOL_BEHAVIOUR_REVISION` is not bumped, and the decision is recorded here rather than
assumed: the tools return the same evidence for the same arguments as before; what changed is
which arguments the agent layer supplies, and no model ever supplied them. A reader who believes
the widened default changes *what a responder could have concluded* should say so and bump it.

### The one clause not built, and where it went

*"The planner may widen a window per hypothesis"* needs a `window` field on `Dispatch`, and
`Dispatch` is part of `DispatchPlan`, whose JSON schema is in `prompts_hash()`. Adding the field
moves the frozen `prompts` key and costs a comparability generation, so it is **Q17**, to land
with the batch that already spends one. `WindowRule` reserves `planner_widened` so the log format
does not change when it arrives. Until then the policy's windows are the only windows, which is
the stronger form of *"never left to agent discretion"*, and the planner's widening is the one
clause of T3.2b still owed.

### The measured ten minutes

The old default's docstring carried a finding worth keeping: three of the ten rehearsed
investigations read logs from *before* onset, and `shipping-wrong-image` says the pre-onset
stream *"is where it breaks open"*. Ten minutes was the least that finding required; the plan's
thirty is wider on exactly the side it cares about, and the forward end now reaches the moment of
investigation instead of stopping five minutes after the alert. The finding is honoured, not
discarded, and it lives on in `window.py`'s module docstring.

## Addendum (T3.4, 2026-09-02) — change candidates are ranked in the tool

The plan's T3.4, *Change analyst*: *"Specialist over change sources: recent deploys, config
changes, feature flags, git diffs near the incident window, ranked by suspicion."* Method:
*"Deploy-history and repo-compare tools; time-proximity plus blast-radius ranking of candidate
changes."* Deliverable: *"Ranked suspicious-change evidence per incident."*

What existed: `change_history` returned a service's records oldest first, and whatever ranking
happened was the specialist's reading of timestamps in a user message. The Phase 3 audit
recorded the task as *partial* on two counts — no ranking, no repo-compare.

### What is built

`faultline/tools/ranking.py`. `change_history` takes an optional `RankingContext` — alert onset
and triage's blast radius keyed by canonical service — and with one, returns the records **in
rank order**, each row carrying `rank`, `lead_seconds` (positive means the change preceded
onset) and `causal` (`before_onset` / `after_onset`), and the result carrying the queried
service's `standing` in the radius: `direction`, `hops`, `reason`. The envelope shows
`#1  4m before onset` per row and `radius="seed" hops="0"` in its opening tag, so the
synthesizer sees the ranking where it sees the evidence. Without a context the tool answers
exactly as before — oldest first, unranked — so a dry run or a replay without triage is
unchanged.

The context is built **once per investigation** in `Investigation._run`, read off
`TriageResult` rather than recomputed: direction, hops and entry reason are triage's claims,
and the ranking rests on the same radius the verdict is judged against. Every change dispatch
of the investigation is then ranked by one rule against one onset and one radius, which is what
makes the evidence *per incident*: two results the synthesizer holds side by side are on one
scale.

### The rule, and why it is an ordering rather than a score

`rank_key` is a lexicographic sort with four keys, in this order: **causal tier** (a change
after onset cannot have caused the onset, and ranks below every change that could — it is still
shown, because a revert after onset tells a responder someone already tried something);
**radius tier** from triage's `Direction` (`candidate_cause`, a callee of an alerting service,
above `seed`, above `also_affected`, above a service outside the radius — the tiers follow what
ADR-0017's directed `sync` measurement licenses and nothing more); **hops**, fewer first;
**lead**, closer first. One dispatch queries one service (T3.4c), so within a single result the
radius tier is constant and the order is causal tier then lead.

No decay constant, no weights, no probability. There is nothing to fit one to: the recorded
corpus has one injected change per scenario, so any numeric suspicion score would be an
invention presented as a measurement. An ordering with every key stated can be read back by a
test and argued with by a reader; a score cannot.

### What this does and does not move

Nothing frozen. `tool_surface()` reads method names and none changed; `capability_version` is
`cap:9c416e0a` before and after, `prompts` digest `1b0e7cbb4c47` before and after. The
`ranking` parameter is keyword-only in practice and defaults to `None`.

`TOOL_BEHAVIOUR_REVISION` is not bumped, and the decision is recorded rather than assumed. The
set of records a call returns is unchanged; the annotations are derived from each record's own
timestamp and from triage output a responder already held, and the rehearsal narratives were
written by people who had both. A reader who holds that a *ranking* changes what a responder
could conclude — rather than how fast — should say so and bump it, which moves the `world` key.

### What is still owed

The **repo-compare / git-diff tool**. The plan names it in the method column and the audit
recorded its absence. It is a fifth tool, so it moves `tool_surface()` and therefore
`CAPABILITY_VERSION` and the frozen `world` key; it belongs to the batch that already spends a
generation (Phase 3 Batch B), beside Q17. It is also a tool this world cannot yet feed: the OTel
demo's services are pulled images, not checked-out repositories (ADR-0026), so what a
"repo-compare" compares here is the image and configuration history the change log already
records. That is a design question for Batch B, not a reason to skip the ranking that was free.
