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

**An ambiguous label is reported as such, not quietly scored.**
`expected_remediation_class` is drawn from four values — `rollback`, `restart`,
`config_revert`, `scale` — and the two `dependency_latency` scenarios do not have a clean
answer among them. An injected netem delay on a container's own interface is not fixed by
rolling anything back, reverting any configuration, or adding capacity to a dependency that
is not overloaded. Both are labelled `restart`, on the reading that recreating the container
is what clears a bad network path. That is the least-bad fit, not a correct answer.

T4.2 must therefore report remediation-class accuracy **broken out by fault class**, never
only in aggregate. If agents systematically miss the remediation class on
`dependency_latency` and nowhere else, that is a labelling artifact of this ADR's own
making, and a single aggregate number would present it as an agent failure. The breakdown
is what makes the two distinguishable, and the cost of not having it is misattributing our
own labelling problem to the system under test.

The same applies to any label we later find ourselves arguing about: the response is to
report the class separately and say why, not to pick a value and hope the ambiguity
averages out.

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

The `dependency_latency` label is provisional pending rehearsal, and either resolution
leaves a hole: `scale` stays untested if the label remains `restart`, and if rehearsal
turns it into `rollback` then `restart` is untested as well and `scale` still is. State
which classes are untested alongside any remediation-class number — the count is two of
four in one branch and one of four in the other, and it is never zero at n=10.

**`scale` is exercised by zero scenarios — a known coverage gap.**
Genuine capacity exhaustion means growing demand past a fixed capacity, which needs
sustained load generation rather than a limit that can be changed and changed back in one
command. It is not cheaply injectable with the mechanisms ADR-0007 and ADR-0010 describe,
and it is deferred to T7.1. Recording it here rather than leaving it silently unexercised:
one of the four remediation classes is currently untested, so any claim about
remediation-class accuracy covers three classes, not four, and should say so.

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
