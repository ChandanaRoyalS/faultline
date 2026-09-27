---
origin: scenario:v2-ad-bad-image-tag
split: dev
fault_class: bad_deploy
recorded_from: 2026-09-27T07:09:40+00:00
capability: cap:d2b243e0
onset_to_page: 5m17s
page_to_fix: 5m00s
fix_to_all_clear: 4m01s
---

# Ad deployed on an image tag that was never published

## What was observed

The page was two alerts in the same moment, `ServiceHighErrorRate` on **frontend** and
**frontend-proxy**, 5m17s after the trouble started. The service the failures would turn out to
name was not on it.

The frontend's error ratio had been zero. It was 3% at two minutes, 11% at four, and peaked at 12%
at five, then eased and held between 7 and 10% for as long as the trouble lasted.
Frontend-proxy's followed it, peaking at 11% and holding at 8-10%. The load generator's rose to
between 4 and 7%, and within a minute of the page it crossed the line for a minute of its own,
`ServiceHighErrorRate` on **load-generator**, and dropped back under it. The storefront's latency
barely moved, a p95 of about 42ms going to at most 47. Pages, carts and checkout kept working:
checkout, payment and everything behind them recorded no errors at all, their rates dipping and
recovering with the load generator's own.

About three minutes after the page, `ServiceNoTraffic` fired on **ad**. Ad had recorded no errors
of its own; its traffic had simply run out. Four alerts on four services by the fix, and none after
it.

## What was checked

**The page names callers.** Frontend-proxy forwards what the frontend returns, and the load
generator is the synthetic shoppers counting their own failures. The frontend was the one service
making calls that failed, and the order path was not among them.

**The frontend's error traces.** Among them were the storefront's ad requests:
`load-generator/GET` to `frontend-proxy/ingress` to `frontend/GET /api/data`, the frontend's
`/api/data` route, and beneath it `frontend/grpc.oteldemo.AdService/GetAds` in error, with no ad
span beneath it. The call had gone out and nothing on the other side had answered it.

**The frontend's log.** It said the same in its own words: an `UNAVAILABLE` error, 156 times during
the trouble, up to 24 a minute, where there had been none before, and 14 more in the five minutes
after the fix as it found ad again. `UNAVAILABLE` is gRPC's word for a service the caller could
not get a call through to.

**Ad itself.** It raised no error, because it served nothing. Its traffic did not fall to a failing
level; it fell to zero, and that is what finally paged on it, once its five-minute window had
drained. Its log ended at the moment the trouble began with `*** shutting down gRPC ads server since
JVM is shutting down` and `*** server shut down`, after about sixteen ad requests a minute, 82 in
the five minutes before, and after that there was nothing at all for more than ten minutes. A
service that is failing logs its failures. This one had stopped. Its 51 JVM runtime series did not
stop at once to the eye: they held their last values for five minutes, the store's lookback, and
then disappeared, so for the first minutes they looked like a process that was up and idle.

**A sliver of errors on the flag readers.** A dead end. Ad, fraud-detection, recommendation,
product-reviews and flagd each showed about half a percent to one and a half in the minutes around
the start, and again ten minutes later: their streams to the flag service reconnecting on its
routine timeout. None came near a line, and it had begun before the trouble did.

**What changed.** One record, at the start: `image reference updated on ad`, to
`ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2`. The running ad had been
`ghcr.io/open-telemetry/demo:2.2.0-ad`. The old container was stopped for the new one and no new
one ever ran: the registry has no such tag, so there was nothing to start. Nothing else had changed
on ad or on the frontend.

## Root cause

A deploy moved ad to an image tag, `2.2.0-ad-hotfix.2`, that was never published. The running
container was stopped to make way for it and the replacement could not be pulled, so ad was absent
rather than unhealthy: nothing answered the storefront's ad requests, and the frontend's `/api/data`
failed with them. Ad sits off the order path, so browsing, carts and orders went on untouched.
Nothing was wrong with the frontend or with anything else.

## Resolution

Ad was rolled back to the published `2.2.0-ad` image. Its JVM was starting a second after the fix
and listening on its port two seconds later, and it served its first ad request about a minute
after that, as the frontend found it again; a new set of 51 runtime series began with it. Ad's
`ServiceNoTraffic` cleared a minute and a half after the fix and the frontend's error ratios
drained with their windows. Everything was quiet 4m01s after the fix, and nothing fired during
recovery.

Class of fix: **rollback**. A deploy was wrong and it was undone. Restarting ad would have found
nothing to restart, and nothing about its configuration needed to change.

## Detection notes

- Onset to first page: **5m17s**. Services on the page: **two**, neither of them ad. By the fix:
  **four**, ad among them.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The frontend was loud and ad was
  silent; its only alert was the absence of traffic, about three minutes after the page.
- Would the page alone have led you to the right service? **No, but one trace does.** The failing
  storefront request ends at a `GetAds` call with nothing beneath it.
- **A missing service does not error; it goes quiet.** An ad service that was failing would have
  recorded its own error spans and logged its failures. This one recorded nothing, its error ratio
  had no calls to be a ratio of, and its traffic fell to nothing.
- **A leaf's outage stays at the edge.** Ad is called only by the frontend, so the storefront paged
  and the order path never moved. A fault that pages only the frontend and its proxy is worth
  looking for among the frontend's own dependencies before anything deeper.
- **A log that ends is evidence.** `server shut down` and then silence says the process stopped,
  and a change at that moment says why.
- **Runtime series that stop do not stop at once.** They held their last values for five minutes
  before vanishing. Flat and then gone is a process that ended, not one that is idle.
