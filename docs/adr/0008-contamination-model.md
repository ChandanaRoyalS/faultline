# ADR-0008: Two-axis contamination model for the scenario catalog

- **Status:** accepted
- **Date:** 2026-08-23

## Context

The scenario catalog is simultaneously the eval dataset, the regression suite, and the
demo script library. It is also self-labeled: we inject every fault ourselves, so the
answer key exists before the question does. That makes two distinct leakage paths
available, and they are not the same problem.

**Axis 1 — cross-scenario leakage.** Prompt text, context-window tuning, retrieval
configuration, and the runbook corpus are all hill-climbed against measured accuracy.
Anything tuned against a scenario has been fitted to it. Reported accuracy over scenarios
used for tuning is training accuracy, and will not survive an interviewer who asks how the
split was drawn.

**Axis 2 — self-reference.** Scenario rehearsals (T1.5) seed the past-incident store
(T2.4b). When scoring scenario S, the nearest neighbour in that store is the rehearsal of
S — a document containing S's true root cause, written in the label author's own words.
The retrieval agent does not diagnose the incident; it looks up the answer key. This is
*within-split* leakage: a dev-set scenario retrieving its own dev-set rehearsal violates no
split rule at all. Axis 1's defence is structurally blind to it.

Both axes must be closed, and each is closed by a different mechanism at a different
phase. Conflating them is how one of them silently goes unenforced.

## Decision

**Axis 1 — split quarantine (this ADR, enforced from T1.6 onward).**
Every scenario carries a `split` field of `dev` or `holdout`, assigned at authoring time,
before the scenario has been rehearsed even once. Target ratio ~70/30, allocated across
fault classes by the table in `evals/scenarios/SPLIT.md`.

The allocation is made against *unnamed slots* — `bad_deploy-1`, `bad_deploy-2`, and so on
— and committed before authoring begins. Authoring fills slots in order. This removes the
selection bias available when a split is drawn over scenarios that already exist: with
named scenarios in front of you, it is very easy to route the awkward one to dev and keep
the clean one for the headline.

No corpus content, prompt revision, context-engineering change, or retrieval setting may
ever be tuned against a holdout scenario. Rehearsal artifacts land in
`evals/scenarios/artifacts/<split>/<id>/`, so quarantine is a path property rather than a
remembered rule. T2.4b seeds the knowledge stores from the dev split only. T4.1's harness
enforces this by checksum and refuses to score a holdout scenario whose artifacts appear in
any corpus.

**Fault selection and slot assignment are separate decisions, in that order.**
The injector ships more faults than the catalog has slots — twelve against ten at n=10 —
so authoring makes two decisions, and conflating them would reopen exactly the selection
bias the unnamed-slot scheme exists to close.

*Which faults enter the catalog* is a catalog-design choice, made on diagnostic diversity:
prefer faults whose investigation paths differ from each other, drop near-duplicates. At
n=10 this excluded `checkout-currency-misconfig`, which is a near-duplicate of
`cart-redis-misconfig` — both are a service pointed at an address that does not answer,
both are found by reading one caller's configuration against a healthy dependency.
`product-catalog-flag-failure` took the slot because it is a distinct shape: the service
that breaks is not the service that changed, so correlating onset against changes on the
failing service finds nothing.

*Which slot each chosen fault fills* is alphabetical by fault id within its class, no
exceptions. This is the decision the split hangs on, so it is mechanical and leaves nothing
to judgement.

The order matters because only the second decision can bias the split, and separating them
makes the first one auditable. For `bad_config` at n=10 the first decision provably cannot
bias anything regardless: the class has zero holdout slots, so every choice of which
`bad_config` faults to author lands entirely in dev. Where a class does have holdout
capacity, the alphabetical rule is what keeps the choice honest — a fault cannot be steered
toward or away from the holdout by picking which of its siblings gets written.

`checkout-currency-misconfig` stays in the injector, unused, as the T7.1 spare. It is not
dead weight and should not be deleted to tidy the gap between twelve faults and ten
scenarios: T7.1 grows the catalog past 30 and every class gets holdout representation
there, at which point a second `bad_config` diagnosis path is worth having.

**Corpus seeding reads one directory and no others.**
T2.4b seeds the knowledge stores from `evals/scenarios/artifacts/dev/` alone. Not from
`evals/scenarios/artifacts/`, not from the repo, and specifically never from `docs/`.

This is not a tidiness rule. `docs/evidence/gate-1/` documents an injection of
`flag-service-bad-deploy` — which the slot table assigns to `bad_deploy-2`, a **holdout**
slot — and it states that fault's root cause, its target service, its detection latency,
and the exact four-service error cascade it produced. Any seeding pass that walked the
repository for markdown would put the answer key to a holdout scenario into the retrieval
corpus, and the split quarantine above would not notice: the file is not an artifact and
lives nowhere near `artifacts/holdout/`.

The path-based quarantine only works if exactly one path is read. Widening the seed input
"just to pick up the runbooks" is how this defect gets reintroduced, so hand-authored
runbooks get their own explicit directory and their own `origin: authored` stamp rather
than being discovered by a filesystem walk.

**Axis 2 — run-time self-exclusion (specified here, enforced at T4.1b).**
Every knowledge artifact carries a provenance stamp: `origin: authored` or
`origin: scenario:<id>`. Retrieval tools accept `exclude_origin`. The harness sets it to
the scenario under test on every scored run and then asserts the filter actually fired; a
scored run where the filter did not fire is marked **invalid**, not annotated. Silent
non-enforcement is precisely how this defect returns after being fixed once.

Hand-authored runbooks (`origin: authored`) are never excluded. They are legitimate
institutional knowledge, which is exactly what a real on-call engineer would have.

**An ambiguous label is reported as such — or resolved by measurement.**
`expected_remediation_class` is drawn from four values: `rollback`, `restart`,
`config_revert`, `scale`. The two `dependency_latency` scenarios initially had no clean
answer among them. An injected netem delay is not fixed by rolling anything back, reverting
configuration, or adding capacity to a dependency that is not overloaded, so both were
labelled `restart` provisionally and flagged as a least-bad fit rather than a correct one.

**That has since been settled by measurement, and `restart` is right.** Pumba binds to the
container present when its sidecar starts, so recreating the target durably clears the
delay: cartservice p95 went 1.9ms baseline -> ~650ms under fault -> back to 1.9ms after
`docker restart`, and stayed there with the sidecar still running (ADR-0007). Restarting
the service genuinely resolves the incident. The provisional marking has been removed from
both scenarios.

The general rule stands, because the next ambiguous label will not resolve this cleanly:
T4.2 must report remediation-class accuracy **broken out by fault class**, never only in
aggregate. If agents systematically miss one class and nowhere else, that may be a labelling
artifact of our own making, and a single aggregate number would present it as an agent
failure. The response to a label we find ourselves arguing about is to measure it if we can,
and otherwise to report the class separately and say why — never to pick a value and hope
the ambiguity averages out.

**The remediation-class distribution is skewed, and the skew is structural.**
At n=10 the labels fall out as `config_revert` 5, `rollback` 3, `restart` 2, `scale` 0.

`config_revert` covers half the catalog, and that is not an authoring accident. A
self-injected benchmark is biased toward it by construction: injecting a fault *is* making
a change, so undoing that change is usually the correct action. All three
`resource_exhaustion` scenarios reduce a previously adequate limit, which makes restoring
the limit a config revert rather than a scaling decision — `scale` is the answer when
demand grows past capacity, and in these nothing grew. Labelling them `scale` would mark an
agent wrong for correctly reading the limit change out of change history, which is exactly
the diagnosis we want.

The consequence is that **remediation-class accuracy is a weaker discriminator than
root-cause accuracy and must not be headlined on its own.** An agent that answered
`config_revert` to everything would score 50% on it while diagnosing nothing. Report it
alongside root-cause accuracy and alongside the per-class breakdown above, never as a
standalone figure.

The `dependency_latency` label is now measured rather than provisional, so the count of
untested classes is settled at **one of four: `scale`**. `restart` is exercised by the two
`dependency_latency` scenarios and is a correct label for them. State the untested class
alongside any remediation-class number.

**`scale` is exercised by zero scenarios — a known coverage gap.**
Genuine capacity exhaustion means growing demand past a fixed capacity, which needs
sustained load generation rather than a limit that can be changed and changed back in one
command. It is not cheaply injectable with the mechanisms ADR-0007 and ADR-0010 describe,
and it is deferred to T7.1. Recording it here rather than leaving it silently unexercised:
one of the four remediation classes is currently untested, so any claim about
remediation-class accuracy covers three classes, not four, and should say so.

**What the split quarantines is the fault, not the service.** *(Note added after the
catalog was authored. It changes no decision above and moves no scenario.)*

The split quarantine above says:

> No corpus content, prompt revision, context-engineering change, or retrieval setting may
> ever be tuned against a holdout scenario. Rehearsal artifacts land in
> `evals/scenarios/artifacts/<split>/<id>/`, so quarantine is a path property rather than a
> remembered rule. T2.4b seeds the knowledge stores from the dev split only. T4.1's harness
> enforces this by checksum and refuses to score a holdout scenario whose artifacts appear
> in any corpus.

Every clause is about one scenario's artifacts and about tuning. Read exactly, it supports
one claim, and the split does deliver it: **when a holdout scenario is scored, that fault is
unseen** — its rehearsal, its answer key, and anything fitted to it are all out of reach.

It does not support the claim a reader may carry away from "held-out": that the **service**
in the holdout incident is unseen. Nothing above quarantines a service, and nothing above
says it does — the wording is scoped to artifacts and does not overclaim. But it never
states the limit either, and the limit is easy to assume away; `SPLIT.md`'s talk of
"generalisation" is about diagnosis paths across fault classes, not about service novelty.
So state it plainly: a holdout result is evidence of generalisation to an **unseen fault on
a possibly familiar service**.

**Measured at n=10: no service is targeted on both sides of the split.** Blocked scenarios
are excluded, because a scenario that is never rehearsed produces no bundle and so has
nothing to leak. The comparison is by canonical service identity
(`injector.world.canonical_service`) rather than by raw target string, because targets do
not name services consistently: a fault addresses a container (`cart-service`) or a compose
service (`cartservice`) depending on its mechanism, so a dev scenario on
`product-catalog-service` and a holdout one on `productcatalogservice` would compare as
disjoint while sharing a service. Here canonicalisation confirms the raw answer rather than
extending it — raw comparison finds exactly one collision, `featureflagservice`, whose
holdout side (`flag-service-bad-deploy`) is blocked and drops out on that ground alone.
`tests/test_contamination.py` keeps this measured rather than assumed.

**No target-based check can see the case that does cross.**
`product-catalog-flag-failure` is a dev scenario whose target is `featureflagservice`, but
whose narrative is almost entirely about `productcatalogservice`: "product catalog error
ratio rises to a stable, partial fraction of its traffic", "product catalog's CPU, memory
and latency are all normal", "the fix is at the flag service and the symptom is at product
catalog". And `productcatalogservice` is the target of the holdout scenario
`productcatalog-dependency-latency`. What crosses the split here is what the prose
discusses, not what the target field names, so no check over targets — canonical or
otherwise — can detect it. Nor could a stricter split rule, since the two scenarios do not
share a target to be split on.

Whether that is contamination is genuinely open, and it is recorded rather than decided.
It could help an agent legitimately: the dev incident teaches who calls product catalog and
what its normal error ratio, CPU and latency look like, which is context, not an answer. It
could also mislead: the dev incident's cause is a feature flag at a service product catalog
merely calls, while the holdout incident is a pure-latency fault with no error-rate change
at all, so an agent anchored on the retrieved incident would go looking at the flag service
for a fault that is not there. Real responders do retrieve past incidents on the service in
front of them, which makes same-service retrieval arguably realistic rather than leaky — so
this is not asserted to be a defect, and nothing is moved on account of it. It is a
statement of what a holdout number covers, to be made alongside the number.

**Headline policy.** Until the catalog reaches 30+ scenarios, published numbers are
full-set with the dev/holdout breakdown shown and `n` stated explicitly. A 3-scenario
holdout is an anecdote and will not be headlined as anything else. Once T7.1 brings the
holdout to ~9–10 scenarios, the headline switches to holdout-only.

## Consequences

Easier: accuracy claims are defensible under direct questioning, and the two most common
self-labeled-benchmark failures have named owners and mechanical enforcement rather than
good intentions. The ablation work in P7 inherits a clean measurement substrate for free.

Harder: the holdout is unusable for debugging, so roughly a third of the catalog cannot
help when accuracy is disappointing and the reason is unclear. Authoring is slower, because
slot allocation is fixed before the scenarios are known and an interesting scenario cannot
be moved to the split where it would be more convenient.

Accepted asymmetry: at n=10 a 3-scenario holdout cannot cover four fault classes. One class
is dev-only, recorded in `SPLIT.md` with its reason. Full class coverage in the holdout
arrives at T7.1.

Live hazard: `docs/evidence/gate-1/` is a holdout scenario's root cause sitting in the
repository in plain markdown, and it has to stay there — it is the Gate 1 evidence. It is
quarantined by the seeding rule above rather than by its location, which makes it the one
piece of contamination surface not enforced by a path. When T2.4b lands, its seeding input
needs a test that fails on any path outside `evals/scenarios/artifacts/dev/`.

Revisit if: the catalog grows past ~30 and the ~70/30 ratio starts wasting scenarios that
would be worth more as dev-set signal, or if a fifth contamination axis appears (the
likeliest candidate is judge contamination — an LLM judge that has seen the label rubric
during its own prompt tuning).
