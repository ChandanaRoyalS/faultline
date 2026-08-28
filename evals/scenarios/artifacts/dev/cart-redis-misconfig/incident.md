---
origin: scenario:cart-redis-misconfig
split: dev
fault_class: bad_config
recorded_from: 2026-08-28T03:22:17+00:00
onset_to_page: 2m46s
page_to_fix: 5m00s
fix_to_all_clear: 2m46s
---

# Cart service pointed at the wrong Redis port

## What was observed

The page named one service: `ServiceHighErrorRate` on **loadgenerator**, 2m46s after the
first bad request. **frontend** and **checkoutservice** joined fifteen seconds later.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

Then, three and a half minutes after the page, seven services went quiet — six together
at T+6m00s (accountingservice, currencyservice, emailservice, frauddetectionservice,
quoteservice and shippingservice), and **cartservice** fifteen seconds after them. All
`ServiceNoTraffic`.

Ten alerts across ten services.

## What was checked

**Error rate by service.** loadgenerator, frontend and checkout were over threshold.
cartservice showed no errors at all — flat zero, below every healthy service in the
system. That reading was taken as evidence cart was fine.

**loadgenerator.** Set aside. It is the synthetic client, so its error rate mirrors
whatever the storefront is doing and carries no information about cause. Note that it
paged first and alone here, which makes the first page the least informative moment of
the incident rather than the most.

**Traces from frontend.** Checkout spans failing on their call to cart. The first real
narrowing, roughly three minutes in.

**The gap between the errors and the silence.** The error alerts fired at T+2m30s to
T+2m45s; the silence did not arrive until T+6m00s. Those are the same failure at two
different thresholds — `ServiceHighErrorRate` responds to the requests that fail, and
`ServiceNoTraffic` only once the calls stop arriving at all and a rate window empties.

**The fifteen seconds between the six and cartservice.** Tempting to read as ordering —
the six knocked over, then cart. It is not, and the direction is backwards: cart was the
cause and appears *last*. Both groups stopped being called at effectively the same
moment and their rate windows emptied a scrape apart. **Fifteen seconds at this
granularity is a scrape boundary, not a causal sequence.**

**The seven quiet services.** This is where the time went. Seven going silent at once
reads as a platform-wide event. Six of them are downstream of checkout and went quiet
because checkout had stopped calling them; only one was the cause. What the alerting
does not supply is any indication of which.

**cartservice's logs, which are the whole of it.** Eight `Connecting to Redis` lines
over the window, each naming `redis-cart:6380`, and seven unhandled exceptions between
them — `Wasn't able to connect to redis`, with the stack ending in
`RedisCartStore.EnsureRedisConnected`. Eight connection attempts is eight starts; seven
crashes is what happened to the first seven. The cycle is legible from the log alone:
the process starts, checks its Redis connection, fails that check, exits, and comes
back to do it again.

Note what carries this and what does not. The restart loop is not read off a restart
count — it is read off the repetition in the stream, which is the same evidence a
responder without host access would have. And the address is *in the log line*, so the
wrong port is named before any change record is consulted.

**Recent changes to cartservice.** `REDIS_ADDR` set to `redis-cart:6380`. Redis was
listening on 6379 and healthy throughout — every other consumer of it was unaffected.

## Root cause

cartservice was configured with the wrong Redis port. The dependency was never
unhealthy; only the address was wrong.

Because cart validates its Redis connection during startup rather than on first use, the
wrong address stopped the process coming up at all. Cart did not degrade — it
disappeared. That is why it never appeared in the error-rate metric: a service that is
not running records no calls, and therefore no errored ones. Its apparent good health
was an absence of data, not an absence of problems.

## Resolution

`REDIS_ADDR` restored to `redis-cart:6379`. cartservice came up on its next restart and
the no-traffic alerts cleared — those six services had never been broken, only starved.
Everything was clear at **T+10m32s**, 2m46s after the fix.

Class of fix: **config_revert**. Nothing had been deployed and there was no version to
roll back to — one environment value was wrong.

## Detection notes

- Onset to first page: **2m46s**.
- Services alerting at the page: **1**. Over the whole incident: **10**, across 10
  alerts.
- Alerts that fired only during recovery: **none**. Every alert in this window belongs
  to the failure itself.
- **The broken service was not singled out by any alert, but it was not quite lost in
  the crowd either.** cartservice was the only service in the later `ServiceNoTraffic`
  group, fifteen seconds behind the other six. That is a difference a responder can see —
  and the scrape-granularity note above is the reason not to trust it: fifteen seconds
  here distinguishes nothing causally, and a responder who read cart's lateness as
  meaning it fell over *last* would have had the direction exactly reversed.
- Did the loudest service turn out to be the culprit? **No.** loadgenerator alerted
  longest at 7.8 minutes and frontend at 7.5, and neither was broken.
- Would the page alone have been enough? **No.** It named a single service, the synthetic
  client, which is the one service in the system guaranteed to be reporting somebody
  else's failure.
- **A restarting process is a talkative one, and the repetition is the evidence.** Eight
  identical connection attempts and seven identical crashes say "this is starting over and
  over" without any need to ask the host how many times it restarted. A service that is
  killed before it can speak, or that stops and never returns, leaves a differently shaped
  stream — so "the logs are empty", "the logs stop dead" and "the logs repeat" are three
  findings, and telling them apart narrows the cause before anything else does.
- The most misleading signal was cart's own error rate: a flat zero throughout, read as
  health when it meant absence.
