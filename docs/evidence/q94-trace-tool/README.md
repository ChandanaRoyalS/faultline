# Q94 - the trace tool on v2: the replay over every recorded window Tempo still held

**2026-09-24, $0, no model call.** `hops.py` in this directory, run twice through the trace
tool itself (`FAULTLINE_TOOLS_WORLD=v2 uv run python hops.py`). For every trace it prints the
degrading hop under the rule as it stood (rules 1-2, `spantree.error_or_self_time_hop`) and
under the rule with rule 0 (`spantree.degrading_hop`). The terminal output of each run is kept
verbatim beside it.

| file | run against | what it showed |
|---|---|---|
| `replay-1-first-cut.txt` | 0164, the first cut of rule 0 (it skipped erroring spans) | the freeze's hops moved from the proxy's timeout to frontend's call into the catalog. **Two regressions**: on R3 and R5, rule 1 had rightly named a long *erroring* call (`checkout -> ProductCatalogService/GetProduct`, `PlaceOrder -> orders publish`), and the first cut moved the hop one level up to its non-erroring parent. Its "healthy" control covered the last 30 minutes, reached back into the freeze, and replayed freeze traces as healthy ones |
| `replay-2.txt` | 0165, rule 0 keeping a waiting call however it ended; the control from 17:15 | the result below |

## What the second replay shows

| window | traces | callee moved | same callee, wait added | reading |
|---|---:|---:|---:|---|
| R1, R2, R4 | - | - | - | **no traces**: older than Tempo's recreate after the Q95 fix. A limit of this replay, not a pass |
| R2b freeze | 2 / 2 / 7 (frontend / frontend-proxy / product-catalog) | all | 0 | rules 1-2 named `product-catalog/GetProduct` or `ListProducts`, errors of 3-210 ms. Those are the catalog's own requests served *after* the resume, most likely failing on the Postgres restart Q96 then caused (R2b logged 568 `Product Not Found` in the 90 s after it). Rule 0 names frontend's call into the catalog, still waiting up to 651 s, or its call into recommendation. The old answer named the right service for a recovery-phase reason. The new one names the hang |
| R3 partition | 12 | 0 | 12 | rule 1's callee kept in every trace (the long erroring `GetProduct` into the cut-off catalog), with the wait added: 253-641 s after the proxy gave up |
| R4b corruption | 2 / 3 | 0 | 0 | untouched |
| R5 disk fill | 4 | 1 | 3 | `PlaceOrder -> orders publish` kept in three with the wait added. In the fourth, rule 1 had only the proxy's timeout, and rule 0 names `frontend -> checkout/PlaceOrder`, waiting 56.5 s |
| freeze bundle | 10 / 9 / 6 | all | 0 | from `load-generator/GET -> frontend-proxy/ingress` to `frontend/grpc.oteldemo.ProductCatalogService/GetProduct` (or `.../RecommendationService/ListRecommendations`), still waiting 169-517 s. The drawn trace shows the whole chain at v2's depth, down to the catalog's own `GetProduct` arriving 494 s in and served in 118 ms |
| control from 17:15 | 14 / 4 / 11 (all traces); no error traces | 0 | 0 | untouched |

**Rule 0 moved the callee only in the three windows that are hangs, and there it moved it
closer to what stopped answering or kept it where rule 1 already had it.** It moved nothing on
the corruption window or on the healthy control.

**One property to know, not a defect.** Where an intermediate service queues requests behind
workers already blocked on the frozen one, its own spans for a queued request begin only after
the resume. They did not start before the deadline, so rule 0 cannot count them as waiting,
and the hop stops at the call *into* the intermediate: `frontend -> recommendation` in 3 of
10 frontend traces on the freeze, and in the R2b traces where the old rule named
`recommendation -> product-catalog/ListProducts`. The trace itself holds no earlier span that
could say more, and the other traces in the same window name the catalog.
