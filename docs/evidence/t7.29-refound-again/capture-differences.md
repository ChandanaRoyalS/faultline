# What actually changed in the captures, measured

**Why this exists.** The sweep must say whether any movement traces to a documented capture
difference rather than to the agent or the world. That requires knowing exactly which captures
changed, measured from the bundles rather than inferred from T7.28's prose.

Measured by comparing each dev bundle's `alerts_over_window` against the newest archive under its
own `superseded/` directory — the recording S6 (and, for `shipping-quote-misconfig`, T7.24) actually
scored against.

## Triage scores against distinct services, not alert episodes

Verified from S6's stored manifests: `cart-bad-image-tag` carries **12 alert episodes across 10
services** and its `n_alerted` is **10**. So an extra episode on an already-alerting service does
not move the denominator; only a change in the *set* of alerting services does.

## The result — two scenarios, not four

| scenario | alert episodes | alerting services | triage denominator |
|---|---|---|---|
| `ad-memory-squeeze` | 3 → 3 | **unchanged** (3) | unchanged |
| `cart-bad-image-tag` | **10 → 12** | **unchanged** (10) | **unchanged** — both new episodes fall on services already alerting |
| `cart-dependency-latency` | 4 → 4 | **unchanged** (4) | unchanged |
| `cart-redis-misconfig` | 10 → 10 | **unchanged** (10) | unchanged |
| `frauddetection-memory-squeeze` | 1 → 1 | **unchanged** (1) | unchanged |
| **`product-catalog-flag-failure`** | 4 → 4 | **3 → 4** — `checkoutservice` joins | **grows** |
| **`shipping-quote-misconfig`** | **2 → 7** | **2 → 7** — `accountingservice`, `emailservice`, `frauddetectionservice`, `frontend`, `quoteservice` join | **grows sharply** |
| `shipping-wrong-image` | 8 → 8 | **unchanged** (8) | unchanged |

## This corrects the pre-registration, and the correction is the useful part

**The pre-registration named four dev scenarios whose alert composition stage 3 corrected, and
expected triage movement on all four. Only two of them can move for capture reasons.**

The four were named correctly — they are exactly the dev entries in stage 3's corrections table
whose subject is alerting. But **two different things were run together under "alert composition"**:

- **A changed alerting-service set** — `product-catalog-flag-failure` (3 → 4) and
  `shipping-quote-misconfig` (2 → 7). These move the triage denominator, and triage movement here
  is arithmetic.
- **A corrected claim about alert *timing*** — `cart-dependency-latency` (narrative said two
  services with frontend joining later; frontend was at fire) and `cart-redis-misconfig` (said one;
  frontend was at fire). **The narrative prose was wrong and stage 3 fixed it. The set of alerting
  services was the same both times.** Triage never read that prose, so its denominator does not
  move, and any triage movement on these two is *not* capture-attributable.

**So the controls are wider than registered.** Six scenarios have an unchanged triage denominator,
not four: the four originally named plus `cart-dependency-latency` and `cart-redis-misconfig`.

**`cart-bad-image-tag` is the case that shows why episodes had to be separated from services.** It
gained two alert episodes — the only scenario besides `shipping-quote-misconfig` whose episode count
moved — and its triage denominator still does not change, because both fell on services already in
the set. Counting episodes would have predicted movement that cannot occur.
