# Repair replay — dev sweep 12's proposals, executed

Scored apart from diagnosis (`PREREGISTRATION-T6.2.md` §4). R = 1 on a deterministic operation; the proposals were written by an agent that could not act and had finished. **No model call was made.**

**Recovered 6 of 7 executed**; 2 refused; 0 error(s); n = 9 triples.

| scenario | action → target | result | detail |
|---|---|---|---|
| shipping-wrong-image | `rollback_image` → shippingservice | **recovered** | alerts clear after 120s of 300s |
| cart-bad-image-tag | `rollback_image` → cartservice | **refused** | unexecutable: cartservice shows no drift from its declared definition on image; there is nothing to rollback |
| cart-redis-misconfig | `revert_config` → cartservice | **recovered** | alerts clear after 120s of 180s |
| shipping-quote-misconfig | `revert_config` → shippingservice | **recovered** | alerts clear after 123s of 300s |
| payment-telemetry-blackout | `revert_config` → paymentservice | **recovered** | alerts clear after 31s of 600s |
| frauddetection-memory-squeeze | `revert_config` → frauddetectionservice | **recovered** | alerts clear after 30s of 300s |
| ad-memory-squeeze | `revert_config` → adservice | **recovered** | alerts clear after 60s of 300s |
| cart-dependency-latency | `revert_config` → cartservice | **refused** | unexecutable: cartservice shows no drift from its declared definition on environment, memory, nano_cpus; there is nothing to config_revert |
| redis-cart-dependency-latency | `restart_service` → cartservice | **not-recovered** | alerts still firing after 180s; fault still in force; stop --all still reverted ['redis-cart-dependency-latency'] |

Refusals are facts about the executor's model of the world or about the proposer's target, not about whether the fix would have worked:

- **cart-bad-image-tag**: unexecutable: cartservice shows no drift from its declared definition on image; there is nothing to rollback
- **cart-dependency-latency**: unexecutable: cartservice shows no drift from its declared definition on environment, memory, nano_cpus; there is nothing to config_revert
