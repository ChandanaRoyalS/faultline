# ADR-0021: Verdict grounding — every dispatch in the brief, contradictions flagged, and logs kept from both ends

- **Status:** accepted
- **Date:** 2026-08-25
- **Task:** T3.4b, from two defects recorded by T3.4's live smoke
- **Amends:** ADR-0019 §logs (truncation direction), ADR-0020 §2 (role inputs)

## Context

T3.4 ran the first end-to-end investigation against a live `shipping-wrong-image` injection.
It reached the right answer — `bad_deploy` / `rollback`, matching the recorded ground truth —
and its evidence trail recorded two separate ways the answer was reached on worse grounds than
the run actually held. Both are in `docs/evidence/t3.4-first-investigation/README.md`.

**One.** The verdict's highest-value open question was "No change history has been queried for
shippingservice at all — the changes dispatch targeted quoteservice." The query existed:
`tr_f536225dc17d`, dispatched in round two, read at high confidence by the changes specialist,
naming the image swap and its timestamp outright.

Diagnosis, from the stored trajectory before anything was changed:
`InvestigationResult.findings` was `{run.specialist: run.findings for run in self.runs}`. Three
`changes` dispatches over three services collapsed to the last, `quoteservice`, which was
empty. The `checkoutservice` and `shippingservice` change records were dropped before the
synthesizer was called. **The claim was accurate about what the synthesizer was shown.** It was
a context-assembly defect, not an attention defect, and the brief compounded it: findings were
labelled `[changes]` with no service, so three dispatches over three services were
indistinguishable even in principle.

**Two.** The logs specialist reported that shippingservice "emitted nothing for the first ~7
minutes" of its window. Querying Loki directly for the same selector and interval returns 312
lines — Rust request logs running to 8 seconds before the fault. They were dropped by the
newest-40 cap. `incident.md` for this scenario says the pre-onset stream "is where it breaks
open": the container emits Rust before the boundary and JVM banners after it, and "no resource
limit does that" is the only thing that separates a bad deploy from a memory ceiling. The tool's
own docstring says the same. T2.6's direction fix — keep the newest, because forward-order
truncation returned nothing but healthy pre-onset traffic — is right for the common case and
exactly wrong for the one question that resolves this scenario.

## Decision

### 1. Every dispatch reaches every downstream role, labelled with its service

The planner's follow-up brief, the synthesizer's brief and the scribe's brief take the list of
executed dispatches, not a mapping keyed on specialist. A specialist may be dispatched any
number of times across rounds, at different services, and each of those is a separate piece of
evidence with its own `result_id`.

### 2. The synthesizer's brief indexes the dispatches before the findings

One line per dispatch — `result_id`, specialist, service, counts, first claim — ahead of the
detail. What was queried is stated before what was found, so the shape of the investigation is
readable without inferring it from a scan of findings.

### 3. A verdict that contradicts its trajectory is flagged, never edited

A deterministic check (`agents/grounding.py`) reads the verdict's free text for claims that a
dispatch never happened, and cross-references the executed dispatches. A match becomes a flag on
the investigation carrying the refuting `result_id`, alongside budget exhaustion and lone
specialist failures.

**The verdict text is not touched.** It is evidence of what the model concluded; editing it to
agree with the record would erase the disagreement, and T4.2 has to be able to count these
separately rather than have them silently repaired.

The rule is narrow on purpose: the clause must name a dispatched service, name that dispatch's
evidence type, and negate the *act of querying* before naming it. **An empty result reported as
empty is not a contradiction** — eight of the nine rehearsed narratives turn on a negative
finding, and `empty` and `error` are separate fields on every tool result precisely so that "I
looked and there was nothing" survives as evidence. Negation must precede the verb within one
clause; "the metrics query found no errors" is a result, "no metrics query was run" is a claim
about the investigation. Clauses split on dashes as well as sentence ends, because T3.4's own
sentence named two services and the negation governed only the first.

### 4. Log retention is two-ended, and says so

A log result keeps the newest majority of its budget and a small sample of the oldest, with an
explicit elision marker between them and both counts in the envelope
(`oldest_kept`, `newest_kept`).

**Sizes: a fifth of the budget, floored at 3 lines and ceilinged at 8.** The oldest group is a
*sample*, not a second window — enough to establish what the stream looked like before (three
lines is one JVM startup banner; eight covers a couple of them) while leaving the overwhelming
majority of the budget on the end of the window where the failure is. At the specialist's
`limit=40` that is 8 oldest and 32 newest. Below seven lines there is no useful split and the
result stays one-ended.

Truncation is reported when the two ends demonstrably do not meet. When the window fits inside
the budget the result is one contiguous stream with no marker, as before.

**The boundary is visible as a contrast, not as adjacency.** The two groups are minutes apart
with the marker between them; what the reader can see is that the stream *was* one thing and
*is* another. For `shipping-wrong-image` that is sufficient and is the whole signal.

Traces are unchanged. The defect was in log content and the trace cap is 200 spans, where the
same argument has not been measured.

## Consequences

- T2.6's newest-lines pin keeps its intent and moves its numbers: 7 of 10 retained lines are
  still the end of the window, the middle is still dropped, and a truncated result still cannot
  consist of nothing but pre-onset traffic. The direction pin and the trace pin are untouched.
- The split is *within* the cap, so the token budget is unchanged and the newest group is
  smaller by the size of the sample. A specialist asking for 40 lines now sees 32 recent ones
  rather than 40.
- Two Loki requests per log query instead of one. Both are bounded by the same total.
- Contradiction flags are a new class of flag. T4.2 must report them separately: a flagged
  verdict that is *wrong about its own evidence* is a different failure from one that ran out of
  budget, and pooling them would hide the more interesting of the two.
- The assembly fix removes the cause of T3.4's contradiction; the check covers the case it does
  not. Whether the check ever fires on a run whose assembly is correct is unmeasured, and worth
  reporting from T4.1's first batch.

---

## Addendum (T4.3): §3's contradiction check is retired

**Status of §3 above: superseded.** The rule it established — that a verdict contradicting its
trajectory is flagged rather than edited — is sound and is not being reversed. What is retired is
the *mechanism*: the deterministic clause-parsing check in `faultline.agents.grounding`. Nothing
calls it. The module is kept, unwired, carrying its ledger.

### The evidence, which is the whole argument

ADR-0022 §Consequences set the condition before the batch ran: "If a first batch does not improve
it, the honest options are to narrow it further or to retire it — and either is a decision with
an ADR, not a quiet edit." The first dev sweep is that batch (`evals/runs/SWEEP-2026-08-26.md`).

| run | fired | verdict |
|---|---|---|
| `e7739dec` — T3.4 | 1 | **true positive** |
| `6b9715de` — T3.4b | 1 | false positive |
| `f7afdb76` — T3.4c | 1 | false positive |
| `cart-bad-image-tag` — T4.2 sweep | 2 | false positives |

**0 true positives and 4 false positives live.** And the single true positive does not survive
scrutiny either: T3.4b diagnosed its cause as a **context-assembly defect** — three `changes`
dispatches collapsing to one in a dict keyed on specialist name — and fixed it. The verdict that
check caught was *accurate about what it had been shown*. The defect the check exists to catch
has had **no instance since the assembly fix**, and every firing since has been wrong.

### Why narrow was rejected

Each false positive had a different cause, and each fix was correct and local:

1. a comma-joined clause whose second half said the service *was* covered — split on `, and`;
2. a clause citing the very `result_id` it qualified — skip self-citing clauses;
3. `?` not being a clause boundary, so a service named in a question joined a negation in the
   answer;
4. `image` matching inside `image-pull`, and `flag` inside `flagged`.

Four repairs, four new rules, and a fifth failure would have a fifth cause. **That is what
parsing prose for intent looks like from the inside**: every fix is right and buys one round. The
set of ways an English sentence can mention a service and a negation without claiming a dispatch
never happened is not finite. A check whose precision is maintained by patching a regex is not a
deterministic check — it is a small language model made of regexes, with none of the calibration
and all of the confidence. Narrowing it again would be choosing to keep paying that.

### What is kept, and what would let it back

Kept: the module, its tests, and this ledger. A retired mechanism whose record is deleted gets
rebuilt identically by the next person with the same good idea, and it was a good idea.

The idea worth keeping is that **a verdict makes claims and the trajectory can refute some of
them.** What is not worth keeping is *inferring which claim a sentence is making*.

**Re-admission requires a mechanism that does not parse prose.** The obvious shape is structured:
the synthesizer already returns `open_questions` as a list, and a schema asking for
`unqueried: [{specialist, service}]` beside them would turn the same check into a set comparison
— exactly resolvable, no regex, and wrong only in ways a schema violation already catches. That
is a contracts change, and it belongs to whoever wants the check back, with this ledger in hand.

### Consequences

- `InvestigationResult.contradictions` is always empty from T4.3. The field and the scored
  report's category stay, printing at zero — runs recorded before the retirement still carry
  firings, and a category that disappears takes its history with it.
- T4.2's four reported-separately categories are now four with one permanently empty, and
  `narrative_refused` is the fifth. That asymmetry is honest and better than pretending the
  count is live.
- **The stamp does not move.** `runtime_version` covers the role prompts and the contract
  schemas, and this change touches neither, so the sweep's rows remain comparable to runs made
  after it.
- §4 of this ADR (two-ended truncation) is unaffected and stands.
