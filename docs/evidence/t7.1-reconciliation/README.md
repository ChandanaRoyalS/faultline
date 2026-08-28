# T7.1 stage 3 — what the re-record changed in the narratives

Every narrative was rewritten against its new manifest. This file records **what was corrected
and what was removed**, because the narratives themselves are written in a responder's voice and
are seeded into the retrieval corpus — a "corrections" section inside one would be both out of
voice and a new chunk of harness meta-commentary in the corpus.

The standing rule (`ARTIFACTS.md`): a re-record never overwrites a narrative; a person rewrites
it against the new evidence. Front matter is written to fail on a re-record, prose to survive
one. Both happened here.

## The rule applied

- A claim the new capture **contradicts** is corrected, and the contradiction is named below.
- A claim the new capture **can no longer support** is **removed**, not softened. Three
  observations came out entirely.
- Numbers move wherever the manifest moved. `recorded_from` was set from each manifest
  programmatically after one was transcribed wrongly by hand.

## Removed outright — the capture no longer contains them

| narrative | what was removed | why |
|---|---|---|
| `ad-memory-squeeze` | The whole "crosses, clears, crosses again" observation — frontend's alert dropping under the threshold after thirty seconds and re-firing at T+6m15s, and the detection note built on it | The previous recording had frontend firing **twice** (0.5 min, then 4.5 min). The new one has it firing **once, continuously, for 6.8 min**. The phenomenon is not in this recording, so the lesson drawn from it cannot be either. Replaced with what this recording does show: a partial failure that looks completely ordinary in the alerting, with the storefront — not the metric — being the thing that said "one dependency out of many". |
| `cart-bad-image-tag` | The "two waves fifteen seconds apart" material, in both the checks section and the detection notes | All seven services went quiet in a **single evaluation** at T+6m15s. There is no second wave to misread. Replaced with the gap that this recording does contain — two and a half minutes between the error alerts and the silence, which is one failure crossing two thresholds. |
| `recommendation-memory-squeeze` | Both `ServiceHighLatency` alerts on frontend and loadgenerator, and the claim that pages "took noticeably longer to render" | **No latency rule fired anywhere** in the new recording (5 alerts → 3). Replaced with the stronger observation the absence supports: a dependency the caller can skip rather than wait for produces a failure with no latency signature at all. |
| `product-catalog-flag-failure` | "Recovery time is diagnostic in hindsight — a 48-second all-clear means nothing was restarted… a fault that clears within one scrape interval was a decision, not a state" | Its all-clear is now **1m34s**, and the re-record refutes the reasoning directly: `frauddetection-memory-squeeze`, which **does** require a process to come back, cleared in **1m31s** — faster. The inference from recovery speed to fault kind does not survive its own catalog. |

## Corrected — the capture contradicts what was written

| narrative | claim | now |
|---|---|---|
| `email-wrong-image` | "**emailservice never appeared in the alerting at any point** — not on error rate, not on latency, not on traffic" | It **does** alert: `ServiceNoTraffic` at T+6m15s, 3.2 min. Still late (2¼ min after the page) and still not a failure signal — a container that cannot start serves nothing, so the only rule it can trip is absence. The teaching point survives in weaker form and is stated as such. |
| `cart-redis-misconfig` | "cartservice appeared in the second wave alongside three services merely downstream of it" — indistinguishable from six healthy ones | cartservice is now **alone** in the later group, fifteen seconds behind six others. That is a visible difference, so the "indistinguishable" claim is corrected — and the narrative's own scrape-granularity caution is now load-bearing, because a responder reading cart's lateness as "it fell over last" would have the causal direction exactly reversed. |
| `cart-redis-misconfig` | The page named frontend **and** loadgenerator | The page named **loadgenerator alone** — the synthetic client, the one service guaranteed to be reporting somebody else's failure. |
| `cart-dependency-latency` | "Four alerts fired in the same evaluation… Services alerting at the page: 4" | **Two** paged (cartservice, loadgenerator); checkout and frontend followed fifteen seconds later. The culprit is now one of only two services named at the page. |
| `productcatalog-dependency-latency` | The culprit alerted "thirty seconds after the page and after two of its own callers" | **A full minute** after the page, and after **all four** of its callers — checkoutservice joined the page in this recording. |
| `shipping-wrong-image` | frontend and loadgenerator "crossed the error threshold about a minute later and dropped back under it within a minute" | They alerted **last of all**, at T+6m30s — nearly four minutes after checkout — and stayed up. Dilution is now measurable at that gap, which is a sharper version of the same point. |
| `cart-bad-image-tag`, `cart-redis-misconfig`, `shipping-wrong-image`, `product-catalog-flag-failure` | Recovery-phase alert counts | The recovery `ServiceHighErrorRate` on emailservice is **gone** from the first three. `product-catalog-flag-failure` **gained** one: frontend re-crosses for ~12s after the fix, on a service that was genuinely part of the failure, which makes it harder to dismiss than a recovery alert on a bystander. |

Every narrative's `onset_to_page`, `page_to_fix` and `fix_to_all_clear` moved except
`productcatalog-dependency-latency`'s onset figure. The two INVALID bundles had
`page_to_fix: 5m00s` in front matter despite never having paged; that is now `n/a`.

## On the retention window, and what it shaped

The re-record raised Prometheus retention from **6h to 15d**. Nothing in the narratives had to be
corrected for it — but the honest observation is that **it shaped which questions were askable at
all**, not just which answers were reachable.

`CATALOG.md` records the concrete instance: `runtime.json` could not be backfilled into the
existing ten bundles because their windows were from 08-23 and the Prometheus server had started
08-24T08:53Z. The window was gone before the question was asked. Every detection note in this
catalog that reasons from a metric series was written by someone who could only look back six
hours, and the two narratives that lean hardest on runtime series — `ad-memory-squeeze` and
`recommendation-memory-squeeze` — do so because those were the bundles recorded late enough to
still have them.

**Nothing in the current narratives is known to be wrong because of the old window.** What is
true is that the set of observations available to be written down was bounded by it, and that
bound is now fifteen days wide. That is a statement about what future narratives can contain, not
a correction to these.

## The two INVALID bundles carry no prose to reconcile

`currency-cpu-throttle` and `flag-service-crashloop` still hold the unfilled `incident.md`
template, comment scaffolding and all, because neither has ever produced an incident to write up.
Both were re-recorded, both fired nothing over a 420s wait and across the whole window, and both
recorded reasons were re-verified against the rebuilt world rather than assumed:

- `featureflagservice` still emits **no span metrics at all** — it does not appear in
  `calls_total` — so no fault on it can page.
- `currencyservice` idles at **0.04% CPU**, so a quota ceiling has nothing to bind against.

Neither reason was ever about retention, which is why raising it changed nothing for them. Both
`INVALID.md` files stay.
