---
origin: scenario:cart-bad-image-tag
split: dev
fault_class: bad_deploy
recorded_from: 2026-08-28T02:56:25+00:00
onset_to_page: 4m02s
page_to_fix: 5m00s
fix_to_all_clear: 2m15s
---

# Cart service deployed on an image tag that was never published

## What was observed

The page named three services in the same evaluation: `ServiceHighErrorRate` on
**frontend**, **loadgenerator** and **checkoutservice**. It arrived 4m02s after onset.

On the storefront, product pages rendered normally. Adding anything to a basket failed.

Two and a half minutes after the page, seven services went quiet **together** at
T+6m15s — accountingservice, **cartservice**, currencyservice, emailservice,
frauddetectionservice, quoteservice and shippingservice. All `ServiceNoTraffic`, all in
the same evaluation.

Ten alerts across ten services.

## What was checked

**Error rate by service.** frontend, loadgenerator and checkout were over threshold.
cartservice showed no errors at all — flat zero. Read, wrongly, as evidence cart was
healthy.

**loadgenerator.** Set aside. It is the synthetic client; its error rate restates what
the storefront is failing to do and says nothing about cause.

**Traces from frontend.** Checkout spans failing on their call to cart. The first real
narrowing.

**The gap between the errors and the silence.** Errors alerted at T+3m45s; the silence
did not arrive until T+6m15s, two and a half minutes later. That is not the failure
spreading. `ServiceHighErrorRate` responds to requests that fail, and `ServiceNoTraffic`
only once calls stop arriving at all and a rate window empties — the same event crossing
two thresholds that are sensitive to different things. The seven quiet services were all
quiet for the same reason at the same moment.

**cartservice's logs, which stop rather than complain.** The stream is intact and entirely
ordinary right up to onset, then ends at T+0 with the service's own shutdown lines. For the
whole of the fault it produces **nothing** — three lines inside the window, all of them that
shutdown. The next line arrives one second after the fix went in.

So "check the service's logs" does not return nothing. It returns a full history that ends
mid-sentence at the moment the incident begins, and never resumes. The gap is the evidence,
and it is only visible if you look at where the lines stop rather than at what they say.

**cartservice's own runtime series, which confirm it is gone rather than idle.** A process
that is merely not being called still reports its heap; these stop. **They also date it
badly, and the bundle proves why**: the series carry on for five minutes past a shutdown the
logs place exactly at T+0, at an unchanging value, and then cease. That tail is the metrics
store holding a stale sample forward, not the process living — so runtime series answer
*whether* the service is running and are worth up to five minutes of slack on *when* it
stopped. The logs are what date this one.

**What changed on cartservice, which is where the answer lives.** Its image reference had
been moved to a tag that does not exist in the registry. Nothing else about the service was
touched — environment, configuration, dependencies and resource limits all unchanged, and the
previously deployed image still present and still healthy.

That the pull failed and no container was ever created is an **inference from the change
record**, not something observed: an unresolvable tag and a service that goes away at the same
instant have one obvious explanation. What the evidence to hand shows is that the service
stopped, stayed stopped, and had its image reference changed in the same moment. Whether a
container was created and died instantly or never created at all is not visible from here, and
it does not change the fix.

## Root cause

cartservice was pointed at an image tag that had never been published, and the service
ceased to exist. Redis was fine, the network was fine, the code was fine — there was no
running copy of the code for any of that to matter to.

Its apparent zero error rate was an absence of data. A service that is not running
records no calls, and therefore no errored ones.

## Resolution

The image reference was restored to the previously deployed tag. cartservice came up on
the next reconciliation and the no-traffic alerts cleared — those six services had never
been broken, only starved. Everything was clear at **T+11m17s**, 2m15s after the fix.

Class of fix: **rollback**. A deployment moved the service to a version that does not
exist; the fix was to put the previous version back.

## Detection notes

- Onset to first page: **4m02s**.
- Services alerting at the page: **3**. Over the whole incident: **10**, across 10
  alerts.
- Alerts that fired only during recovery: **none**. Every alert in this window belongs
  to the failure itself.
- **The broken service was indistinguishable from six healthy ones.** cartservice went
  quiet in the same evaluation as six services that were merely downstream of it, and
  nothing in the alerting singled it out — not its position, not its timing, not the
  alert it fired. Alphabetically it is one entry in a list of seven.
- Did the loudest service turn out to be the culprit? **No.** loadgenerator alerted
  longest at 7.2 minutes and frontend and checkout at 7.0, and none of the three was
  broken.
- **Two classes agree, and one of them is precise.** The logs say the service stopped at T+0
  and never spoke again; the runtime series say it is absent rather than idle. Only the logs
  date it — the runtime tail runs five minutes past a shutdown the logs place exactly, which
  is the metrics store holding a stale sample rather than the process living.
- **The shape of the log stream is the strongest evidence available, and both kinds of
  failure leave one.** A service that keeps dying produces continuous failure chatter —
  the same error, over and over, for as long as the incident lasts. A service that was
  never created produces a clean stop and then silence. Both leave a log file, and both
  files are full of ordinary traffic from before onset, so counting lines distinguishes
  nothing. What distinguishes them is **where the lines end and whether anything follows**.
  Here they end at onset with an orderly shutdown and resume one second after the fix,
  which is a container that was stopped and never replaced — not one that is failing.
- **Two thresholds, not two events.** The two-and-a-half-minute gap between the error
  alerts and the silence is the most misreadable feature of this incident: it looks like
  a failure spreading outward from the storefront, and it is one failure being noticed
  twice by rules that measure different things.
