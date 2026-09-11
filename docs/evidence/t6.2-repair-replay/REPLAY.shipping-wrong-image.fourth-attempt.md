# Repair replay — dev sweep 12's proposals, executed

Scored apart from diagnosis (`PREREGISTRATION-T6.2.md` §4). R = 1 on a deterministic operation; the proposals were written by an agent that could not act and had finished. **No model call was made.**

**Recovered 1 of 1 executed**; 0 refused; 0 error(s); n = 1 triples.

| scenario | action → target | result | detail |
|---|---|---|---|
| shipping-wrong-image | `rollback_image` → shippingservice | **recovered** | alerts clear after 120s of 300s |
