# ADR-0040 — which `k` decides a retrieval measurement

**Status:** accepted, 2026-09-14
**Task:** Q47, opened by Q39

## Context

Every retrieval number this repository has published is stated at `k = 5`. The registered floor
(`recall@5 ≥ 0.60`, `MRR ≥ 0.45`) is a `k = 5` statement, the CI gate reads `k = 5`, and
`PREREGISTRATION-Q39.md` §3 made `recall@5` the number that decides whether a change is adopted.

**Production retrieves `k = 3`.** `ContextSettings.retrieval_k` is 3, `Investigation.__init__`
defaults to 3, and `faultline-investigate` uses it. T6.4 set that default *because nothing read the
old value of 5* — the 5 was vestigial, and the floor had been written against it.

T6.4 noticed the mismatch and said so in the `--k` help text: 3 is production's, 5 is what the
floor was written against, *"which are not the same pipeline."* It then registered the floor's `k`
as decisive anyway, and Q39 inherited that.

Q39 is where it cost something. The disjunctive text arm **improved `k = 3` substantially**
(`recall` 0.256 → 0.395, eleven queries answered becoming seventeen) and **lowered `recall@5`** by
one query of 43. The registered rule read the metric that got worse and said do not adopt.

## The problem with fixing this now

We have seen the numbers. `k = 3` is the `k` that favours the change just shipped. **A rule chosen
after seeing which metric flatters you is not a rule**, and ADR-0018 already records four
parameters this repository chose without measurement as the mistake it does not want to repeat.

So this ADR is deliberately narrow about what it changes, and every clause below is either
strictly more demanding than the status quo or independent of any result.

## Decision

**1. The CI gate asserts both `k`.** It asserted `k = 5` only. Adding `k = 3` is additive and
strictly more demanding: nothing that passed before can fail because of a rule that only adds a
condition, and a regression at production's depth is now visible.

**2. The deciding metric for the *next* retrieval change is `recall@3`**, with `MRR@3` as
tie-break, because that is the depth production retrieves at. Registered here, before that
measurement exists. This is the clause that could be self-serving, so its justification is stated
as a fact that does not depend on any result: **a measurement that decides on a configuration the
system does not run is measuring something else.** That was true before Q39 and would have been
true had Q39 gone the other way.

**3. Both `k` continue to be reported, always.** Q48 established that they are not nested — each
arm applies its own `LIMIT k` and `fuse` takes `limit=k`, so the `k = 3` and `k = 5` results are
different retrievals rather than one retrieval read at two depths. Reporting one and calling it the
number would hide that.

**4. The registered floor does not move, and no `k = 3` floor is set.** The floor is `recall@5 ≥
0.60`, `MRR ≥ 0.45`, argued before any measurement existed. We now know `recall@3` is 0.395, so any
`k = 3` floor written today would be a floor chosen with the answer in hand — which is exactly what
a floor is not. **A `k = 3` floor can only be set by someone who has not seen this number**, or
never.

**5. "No measured difference" is one query, not 0.02.** `PREREGISTRATION-Q39.md` §3's tie-break
band was 0.02, and one query of 43 is **0.0233** — so the band was unreachable by construction: a
recall difference is either exactly zero or at least `1/n`. The band is now stated as **one query**,
which is the instrument's actual resolution and scales with the golden set instead of being a
constant someone picked.

## Consequences

**The gate gets stricter today.** Two more assertions against the same measurement.

**Q39's adoption is not retroactively justified by this.** It was adopted under the rule in force,
against that rule's verdict, with the argument recorded in `RETRIEVAL-2026-09-13-q39.md` §4. This
ADR changes what happens next; it does not change what happened. Anyone re-reading that decision
should read §4 and not this file.

**The floor stays unreached and now visibly so at one depth only.** `recall@5` is 0.442 against
0.60. There is no statement of what good looks like at `k = 3`, and clause 4 is the reason.

**A reader can still be misled by a single headline.** Two numbers that are not nested, reported
together, is more honest than one and also harder to quote. That cost is accepted: the alternative
is a headline that was wrong for one of the two pipelines.
