# ADR-0031: Retries, substitutions, and what T2.5 never built

- **Status:** accepted
- **Date:** 2026-09-01
- **Task:** T2.5 (LLM gateway), reached during the Phase 2 audit
- **Relates to:** ADR-0003 (in-house runtime), ADR-0020 §5 (budgets), ADR-0022 (the freeze)

## Context

T2.5's deliverable column reads *"Gateway with fallback, budget enforcement + verified
self-hosted seam."* The Phase 2 audit found that **the string `T2.5` appears nowhere in this
repository** — not in code, not in an ADR, not in `docs/PLAN.md`. Parts of it arrived later
under other task numbers, and the rest never arrived at all.

| T2.5 names | Where it actually is |
|---|---|
| timeouts | `AnthropicModel(timeout=600.0)` |
| per-incident token/dollar budgets | **T3.3**, ADR-0020 §5 — four bounds, exhaustion as a value |
| cost metering | `ModelResponse` carries token counts; runs report dollars |
| retries with backoff | **built here** |
| fallback | **built here**, off by default |
| provider routing | **not built** — one provider, one key |
| verified self-hosted seam | **not built** — the seam exists, the verification does not |

The gap has a measured cost. At T7.58 a pre-registered run died on an Anthropic **529
overloaded_error** and was recorded as a discard, leaving that arm at n = 2 against the n = 3
it had registered. Four retries with backoff would very likely have saved it. That is the
first row of the proposal's own failure-scenario table — *"LLM provider outage / 429 storm"* —
arriving in practice with no mechanism to meet it.

## Decision

**Retrying is transparent. Substituting is not. The fallback list is empty by default.**

`Resilient` wraps any `LanguageModel`. On a transient failure — 408, 409, 425, 429, 5xx, 529,
or a connection/timeout error matched by class name — it retries the same model with full
jitter over a doubling delay, capped. A non-transient failure propagates immediately, because
sending a 400 four times is four 400s.

If the primary is exhausted *and* fallbacks are configured, each is tried in turn, and the
substitution is recorded on the wrapper naming what was replaced, what answered, and the
failure that caused it.

### Why the fallback list is empty rather than populated

Because the freeze would lie.

`freeze.model_map()` reads `AgentSettings.effective_models(...)` — the models a run was
**configured** with. `ModelResponse.model` records the model that **answered**, and the
trajectory persists it per run and per role. Today those two cannot disagree, because nothing
substitutes. The moment a fallback fires silently, the freeze asserts a model that never ran,
while the trajectory records the one that did.

That is exactly the defect T7.54 found in the world digests — a record describing something
other than what happened — relocated into the freeze table. And beyond the bookkeeping: a
fallback model's answer quality has never been measured here, so a substitution mid-sweep
changes what a scored run measures. Enabling it must be a decision, with its consequence
understood, not a default that quietly improves completion rates.

Set `fallback_models` for a demo or a long unattended sweep where finishing matters more than
comparability. Leave it empty for anything scored.

## What this does not close

**Provider routing** is not built. There is one provider and one key, so routing has nothing
to route between; ADR-0004 records that the benchmark target routes through LiteLLM, which is
where a second provider would most naturally arrive.

**The self-hosted seam is designed but unverified.** `LanguageModel` is a Protocol with a
lazy real implementation and a deterministic fake, which is the shape the positioning's
"self-hosted lane" needs — but nothing has ever run this against an OpenAI-compatible
endpoint, and T2.5's deliverable says *verified*. Claiming the lane works would be claiming
an untested thing.

**`model_map` still records intent rather than fact.** Queued as **Q14**: the reconciliation
becomes necessary the first time anyone sets `fallback_models` on a scored run, and pointless
before that.

## Consequences

**Easier.** A 529 burst no longer ends a registered run. The retry path is exercised by ten
tests rather than by a live provider outage, and the wrapper takes an injected sleep and
jitter so the backoff schedule is asserted rather than waited out.

**Harder.** There are now two places that describe which model ran, and they agree only
because substitution is disabled. Q14 is the price of enabling it.

**Verified rather than assumed.** One test failed on first run because its stub was named
`_APIConnectionError` while `is_transient` matches the SDK's actual class name. Name-based
classification is only as good as the name, and the test now carries the SDK's exactly.

## Revisit if

A second provider becomes available — routing and a genuinely independent fallback both
become possible, and the self-hosted seam becomes verifiable at the same time. Also revisit
if anyone proposes enabling `fallback_models` for a scored run, which is Q14's trigger.

## Addendum (2026-09-01) — the self-hosted seam, verified

This ADR closed by recording that *"routing and the verified self-hosted seam remain
unbuilt"*. The seam is now built and run. Routing is not, and the distinction matters enough
to state twice.

### What was built

`OpenAICompatibleModel` — one more implementation of `LanguageModel`, talking to any
chat-completions endpoint: vLLM, Ollama, a gateway, or OpenAI. `build_model()` chooses by
`AgentSettings.provider`, so the lane is a setting rather than a branch in the agent code.
No role knows which one it holds; that is what makes the seam a seam.

It uses `urllib` from the standard library rather than a client package. The claim is that
the seam is thin, and a demonstration of thinness that needs a dependency is a weaker one —
and it is one fewer thing to install on the machine whose reason for existing is that
incident data does not leave its network.

### What was proven, precisely

`tests/test_integration_selfhosted.py` runs an in-process conformant endpoint and asserts:
every field of `ModelResponse` maps from the OpenAI shape; the system prompt arrives as the
**first message** rather than a top-level parameter, which is where Anthropic puts it and
where a silent mistake would drop every role prompt and look like a bad model; a key is sent
as a bearer token and its absence sends no header; `Resilient` wraps the new lane without
knowing what it holds, so the self-hosted path gets the same retries; and the factory refuses
an unknown provider or a missing base URL.

### What was not proven

**vLLM itself.** The endpoint is a conformant stub. Running vLLM needs a GPU-class image and
a model download, and a test nobody can run is worse than one with a stated scope. What is
established is that a conformant endpoint works, which is the property the positioning claims.

**Parity of configuration.** `effort` is Anthropic's adaptive-thinking control and has no
equivalent on this path, so it is dropped rather than shimmed; `tools` are omitted because
tool-calling shapes differ and a translation layer written against no caller is exactly the
unused seam this project keeps finding. The consequence is real and belongs in any comparison:
**a cross-provider ablation is not comparing equal configurations**, and P7's model-tier work
has to say so rather than present two columns as like for like.

**Routing.** Choosing a provider is not routing. The plan's routing is per-role and
cost-aware — cheap model for triage, frontier for synthesis — and `AgentSettings.role_models`
is the map that would carry it. ADR-0020 deliberately left per-role selection to be settled by
T4.2's measured accuracy rather than a cost estimate, and that is still the position. The seam
now spans two providers; nothing yet decides between them per role.

### Addendum 2 (2026-09-01) — the dollar cap, and what is not missing

An audit of Phase 2 first recorded that dollar cost metering was absent from the product. That
reading was wrong and is corrected here rather than deleted.

**T4.3 owns the computation, and says so.** Its method column reads *"Computed from persisted
trajectories and gateway logs; no new instrumentation needed because P2 recorded everything."*
Phase 2 records tokens, model and latency on every step; `evalharness` applies the price table.
That division is the plan's design. Adding a second cost computation inside the product would
create two sources for one number, which is the failure this project spends its audits finding.

**What is genuinely absent is a bound.** T2.5's description names *"per-incident token/dollar
budgets"* and the proposal's runaway-cost row promises *"hard per-incident cap halts agents"*.
`Budget` halts on tokens, wall-clock seconds and dispatch rounds. A model whose price changes
moves what an investigation costs without moving anything the runtime enforces.

**It queues rather than lands.** `freeze.budget_bounds()` returns four keys and is a frozen
key; a fifth re-founds comparability for every scored run. **Q16**, to land with a batch that
is already re-recording. Gate 4's `cost ≤ $2 per incident` is asserted by the harness after a
run, so no gate waits on this.
