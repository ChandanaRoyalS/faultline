---
origin: scenario:v2-ad-flag-failure
split: dev
fault_class: feature_flag
recorded_from: 2026-09-27T05:33:27+00:00
capability: cap:d2b243e0
onset_to_page: 8m31s
page_to_fix: 5m00s
fix_to_all_clear: 0m01s
---

# A feature flag makes the ad service fail one request in ten

## What was observed

The page was one alert, `ServiceHighErrorRate` on **ad**, 8m31s after the trouble started.
Nothing else fired, then or later, and nothing fired after the fix.

It was slow to come because the error ratio hovered around the line. Ad's ratio had been under 1%.
It crossed the line at about three minutes and fell back under at five, seconds short of the
alert's two-minute hold, which restarted it. It was over again from about six minutes, at 5% to 7%,
and fired at 8m31s. The page did not last: at about eleven minutes the ratio dipped to 4.6% and the
alert went out, two and a half minutes before the fix. The ratio was back over, near 8%, in the
last minute before the fix, not long enough to fire again. Ad's request rate did not change.

Around it, almost nothing moved. The frontend's and frontend-proxy's error ratios rose to about 1%,
1.3% at most, far under the line, and no latency changed on the storefront. The storefront worked;
now and then a page's ads failed to load.

## What was checked

**Ad's log, the service on the page.** For every request it logged `Targeted ad request received for
[...]` or `Non-targeted ad request received`, and now and then, straight after, `GetAds Failed with
status Status{code=UNAVAILABLE, description=null, cause=null}`. Counted over the whole incident,
23 of 168 requests failed, between one in ten and one in seven, 0 to 3 a minute, with none
before the change and none after the fix. The failures fell on every
kind of request, targeted and not, across six categories. Nothing distinguished the requests that
failed from the ones that did not.

**The traces.** A failing request ended at ad's own `oteldemo.AdService/GetAds` span, in error,
under the frontend's call to it and the storefront's `/api/data`: 23 such traces over the fault, one
for each failure in the log. The span carries no status message. The error had no description to
give: `UNAVAILABLE` with nothing after it. Ad had chosen the ads, in the same few milliseconds as a
request that succeeded, and then failed. Apart from those, ad's only error spans were two closes of
its own stream to the flag service, the routine ten-minute timeout, which is also why its ratio had
never read quite zero.

**The frontend.** Its log carried the same thing from the other side, `Error: 14 UNAVAILABLE:` with
empty details, 23 times, once for each of ad's failures. The frontend was only passing on what ad
told it.

**Whether ad was unwell.** It was not. Its request rate held, its JVM runtime series reported
without a break, its CPU time and garbage collection were flat, and it restarted nothing. Its p95
rose for a few minutes, from about 5ms to about 40ms, but fell back while the failures went on, so
it did not follow them. A service that is overloaded or failing on a dependency fails more as load
rises, or fails the requests that touch the broken dependency. This one failed a steady fraction of
everything, at random, and told nobody why.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart. A steady, random, fixed fraction of failures with no change behind it and no reason given
is a deliberate branch, and on this world deliberate branches are feature flags.

## Root cause

The `adFailure` feature flag was turned on in the flag service. With it on, the ad service fails one
`GetAds` request in ten with `UNAVAILABLE`, after it has chosen the ads, and the storefront's ad
requests fail with it. Nothing else about the service changed. Nothing was deployed or reconfigured,
and the ad service behaved exactly as written. The fault was the flag's value.

## Resolution

The flag was turned back off. The flag service picks up the change on its own, so nothing was
restarted or redeployed. The failures stopped at once: neither ad nor the frontend logged another.
The page had already gone out before the fix, so everything was quiet one second after it, though
ad's error ratio, a five-minute window, had not drained two minutes later. Nothing fired during
recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

## Detection notes

- Onset to first page: **8m31s**, most of it the ratio hovering at the line and restarting the
  alert's hold once. Services on the page: **one**, ad, the service the flag acts on. By the fix:
  **none**; the page had cleared on its own while the fault went on.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one.
- Would the page alone have led you to the right service? **Yes, but not to the cause.** Ad's log
  and spans say that requests fail and never why.
- **A failure with no reason is a clue of its own.** `UNAVAILABLE` with no description, from a
  service that is up and unstrained, is not what a real outage looks like.
- **A fixed random fraction is a decision, not a degradation.** One request in ten or so, spread
  over every kind of request and steady through the incident, is something choosing to fail. With
  nothing in change history, look for the switch that could choose it.
- **A marginal page is slow, and it does not stay.** A fault that holds a service near the alert's
  line may take several windows to page, can drop under and restart the hold, and can clear the
  page while it is still failing requests. A resolved alert is not a fixed fault.
