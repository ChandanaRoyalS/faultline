# A feature flag makes the ad service fail one request in ten

## The scenario

| | |
|---|---|
| scenario | `v2-ad-flag-failure` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `ad` via `v2-ad-flag-failure` |
| time to page | 8m31s |
| steady state captured | 300s |
| capture window | 2026-09-27T05:28:27+00:00 → 2026-09-27T05:48:59+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+8m31s |
| `t_revert` | T+13m31s |
| all clear | T+13m32s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+8m15s | `ad` | ServiceHighErrorRate | 3.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="ad"}` |

`logs/ad.txt` — 462 lines.

## A look at the logs

From `logs/ad.txt` (---- onset 2026-09-27T05:33:27+00:00 ----):

```
2026-09-27T05:28:48+00:00  2026-09-27 05:28:48 - oteldemo.AdService - no baggage found in context trace_id=fb80d2e638d1d6076fa5f70f9460adfc span_id=227a0dbeea3e9eae trace_flags=01
2026-09-27T05:28:48+00:00  2026-09-27 05:28:48 - oteldemo.AdService - Non-targeted ad request received, preparing random response. trace_id=fb80d2e638d1d6076fa5f70f9460adfc span_id=227a0dbeea3e9eae trace_flags=01
2026-09-27T05:28:54+00:00  2026-09-27 05:28:54 - oteldemo.AdService - no baggage found in context trace_id=26858d8ab0c15b2474069d4754794372 span_id=4b1ce51f1cb7b88a trace_flags=01
2026-09-27T05:28:54+00:00  2026-09-27 05:28:54 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=26858d8ab0c15b2474069d4754794372 span_id=4b1ce51f1cb7b88a trace_flags=01
2026-09-27T05:28:56+00:00  2026-09-27 05:28:56 - oteldemo.AdService - no baggage found in context trace_id=f2baf5b86ef723a326e9dfbffa82b28f span_id=a9df9d1c40d19498 trace_flags=01
2026-09-27T05:28:56+00:00  2026-09-27 05:28:56 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=f2baf5b86ef723a326e9dfbffa82b28f span_id=a9df9d1c40d19498 trace_flags=01
2026-09-27T05:28:56+00:00  2026-09-27 05:28:56 - oteldemo.AdService - no baggage found in context trace_id=78365939951dc7f16117f50f3abdd1b8 span_id=68cc5d955da8d3a4 trace_flags=01
2026-09-27T05:28:56+00:00  2026-09-27 05:28:56 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=78365939951dc7f16117f50f3abdd1b8 span_id=68cc5d955da8d3a4 trace_flags=01
2026-09-27T05:28:58+00:00  2026-09-27 05:28:58 - oteldemo.AdService - no baggage found in context trace_id=e68d03ef0f3ebb1bb1009d874ba73d9f span_id=d19fab0e91541f5b trace_flags=01
2026-09-27T05:28:58+00:00  2026-09-27 05:28:58 - oteldemo.AdService - Targeted ad request received for [books] trace_id=e68d03ef0f3ebb1bb1009d874ba73d9f span_id=d19fab0e91541f5b trace_flags=01
2026-09-27T05:28:59+00:00  2026-09-27 05:28:59 - oteldemo.AdService - no baggage found in context trace_id=34bf09af048c671d92fcd19bdf961a28 span_id=7c99249eed60e610 trace_flags=01
2026-09-27T05:28:59+00:00  2026-09-27 05:28:59 - oteldemo.AdService - Targeted ad request received for [books] trace_id=34bf09af048c671d92fcd19bdf961a28 span_id=7c99249eed60e610 trace_flags=01
```

_441 further lines are in the bundle._

## The incident record

Written from the responder's chair, by someone who did not know the fault class
or that anything had been injected. This text is also corpus material, which is
why it never names the injector.

**It keeps its own clock.** The table above is measured from the injection, which
is the only origin the manifest records; a narrative's `T+` offsets are the
responder's own and start wherever that responder started counting — usually the
page, sometimes the injection, sometimes an event in the logs. The same moment can
therefore carry two different offsets on this page. The absolute timestamps in the
bundle are the tiebreak.

### What was observed

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

### What was checked

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

### Root cause

The `adFailure` feature flag was turned on in the flag service. With it on, the ad service fails one
`GetAds` request in ten with `UNAVAILABLE`, after it has chosen the ads, and the storefront's ad
requests fail with it. Nothing else about the service changed. Nothing was deployed or reconfigured,
and the ad service behaved exactly as written. The fault was the flag's value.

### Resolution

The flag was turned back off. The flag service picks up the change on its own, so nothing was
restarted or redeployed. The failures stopped at once: neither ad nor the frontend logged another.
The page had already gone out before the fix, so everything was quiet one second after it, though
ad's error ratio, a five-minute window, had not drained two minutes later. Nothing fired during
recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

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

---

Rendered from [`evals/scenarios/artifacts/dev/v2-ad-flag-failure/`](../../evals/scenarios/artifacts/dev/v2-ad-flag-failure/) by `faultline-render`. [All bundles](README.md).
