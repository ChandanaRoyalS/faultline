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
