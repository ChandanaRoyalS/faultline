# ⚠ THIS IS NOT A BASELINE

A `cart-redis-misconfig` rehearsal was injected at **06:38:03Z** and cleared at
**06:48:50Z** — inside this measurement's 06:16:32Z–07:01:32Z window. Roughly 13 of the
45 minutes describe an injected incident.

`summary.md` as originally written asserted that incident as quiet-world behaviour. Its
"Alerts that fired on an unfaulted world" table is the rehearsal's alert cascade. Its
error-ratio figures — notably emailservice at mean 4.77%, max 100% — are the fault, not
the baseline.

**Do not cite any figure from `summary.md`.** It is kept only so the invalidation is
auditable; ADR-0009's rule is that an artifact which still looks like evidence is worse
than a missing one, and deleting this one would remove the record of how it went wrong.

## What is usable

`summary-partial.md` re-derives the same statistics over the two quiet spans either side
of the fault, from the same captured JSON. It states its coverage and its exclusion.

## Why the tool did not catch it

`evalharness.baseline` checked for active faults at the start of the window and never
again. It now polls the injector every minute and marks the whole output invalid — in the
manifest, in the summary header, and with a non-zero exit — if a fault is seen at any
point. A capture taken today would have refused to publish these numbers.
