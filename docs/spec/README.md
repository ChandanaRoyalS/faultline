# The source documents

Two PDFs, committed **unmodified**:

- [`faultline-project-proposal-rev8.pdf`](faultline-project-proposal-rev8.pdf) — the Faultline
  Project Proposal, REV 8, 18 pages.
- [`faultline-execution-plan-rev9.pdf`](faultline-execution-plan-rev9.pdf) — the Faultline
  Execution Plan, REV 9 · POST-REVIEW-7, dated 2026-08-21: **8 phases · 58 tasks · 8 gates**,
  16–19 weeks part-time.

## These are evidence about intent, and they are never amended to match what was built

**If the repository and these documents disagree, that is a finding, not a formatting problem.**
The fix is to change the repository, or to record the departure as a decision with an ADR behind
it — **never to edit a specification to agree with the code that missed it.** A plan that is
rewritten to match its outcome cannot be used to judge the outcome, and this project's whole method
is judging outcomes against something fixed.

## Why they arrived at T0.1 and not at T0.1's original date

They were outside the repository until now. **T7.62 tried to audit the build against them and
could not**: neither document was in the tree, and `docs/PLAN.md` — the only plan-shaped file here —
opens by saying it *"is not the plan"* and was reconstructed by harvesting task references out of
the repo itself. Auditing against it would have graded the repository against a document derived
from the repository.

**So for thirty-odd tasks, CLAUDE.md said the work was built against a fixed execution plan that a
contributor could not read and no audit could check.** These files close that. The audit T7.62 could
not perform is now possible; it is not part of T0.1.

## How to refer to them

Cite a task by its id (`T0.1`) and, where the wording matters, quote the deliverable column. **Quote
rather than paraphrase** — [`docs/PLAN.md`](../PLAN.md) is an execution log written *against* these
documents and is not a substitute for them.
