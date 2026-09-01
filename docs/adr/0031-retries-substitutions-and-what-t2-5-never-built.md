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
