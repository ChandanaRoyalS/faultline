# A feature flag makes the ad service fail one request in ten

## The scenario

| | |
|---|---|
| scenario | `v2-ad-flag-failure` |
| fault class | **`feature_flag`** |
| expected remediation | `config_revert` |
| split | `dev` |
| injected at | `ad` via `v2-ad-flag-failure` |
| time to page | 10m31s |
| steady state captured | 300s |
| capture window | 2026-09-26T21:58:16+00:00 → 2026-09-26T22:21:47+00:00 |

The clock below runs from the moment the fault went in.

| | |
|---|---|
| `t_inject` | T+0m00s |
| first alert firing | T+10m31s |
| `t_revert` | T+15m31s |
| all clear | T+16m31s |

## What fired, and when

| when | service | alert | firing for | |
|---|---|---|---:|---|
| T+10m30s | `ad` | ServiceHighErrorRate | 6.0 min | **paged** |

## What the bundle contains

| capture | query |
|---|---|
| `metrics/alerts-firing.json` | `ALERTS{alertstate="firing"}` |
| `metrics/call-rate.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/error-ratio.json` | `sum by(service_name) (rate(traces_span_metrics_calls_total{status_code="STATUS_CODE_ERROR"}[5m])) / sum by(service_name) (rate(traces_span_metrics_calls_total[5m]))` |
| `metrics/latency-p95.json` | `histogram_quantile(0.95, sum by(service_name, le) (rate(traces_span_metrics_duration_milliseconds_bucket{span_kind!="SPAN_KIND_INTERNAL"}[5m])))` |
| `metrics/runtime.json` | `{__name__=~"go_.*|dotnet_.*|jvm_.*|process_.*|v8js_.*|nodejs_.*",service_name="ad"}` |

`logs/ad.txt` — 509 lines.

## A look at the logs

From `logs/ad.txt` (---- onset 2026-09-26T22:03:16+00:00 ----):

```
2026-09-26T21:59:51+00:00  2026-09-26 21:59:51 - oteldemo.AdService - no baggage found in context trace_id=5a3a28080d77fd74cfe9151169a51d08 span_id=2ff4ee7899a1ca79 trace_flags=01
2026-09-26T21:59:51+00:00  2026-09-26 21:59:51 - oteldemo.AdService - Targeted ad request received for [travel] trace_id=5a3a28080d77fd74cfe9151169a51d08 span_id=2ff4ee7899a1ca79 trace_flags=01
2026-09-26T21:59:52+00:00  2026-09-26 21:59:52 - oteldemo.AdService - no baggage found in context trace_id=72ec4d289cd4d99c42af4e6d6da99371 span_id=5840254e32259c7e trace_flags=01
2026-09-26T21:59:52+00:00  2026-09-26 21:59:52 - oteldemo.AdService - Targeted ad request received for [binoculars] trace_id=72ec4d289cd4d99c42af4e6d6da99371 span_id=5840254e32259c7e trace_flags=01
2026-09-26T21:59:52+00:00  2026-09-26 21:59:52 - oteldemo.AdService - no baggage found in context trace_id=a0a72e6378c38f56a24e446c43e4c154 span_id=c1b44be0f1aeb260 trace_flags=01
2026-09-26T21:59:52+00:00  2026-09-26 21:59:52 - oteldemo.AdService - Targeted ad request received for [assembly] trace_id=a0a72e6378c38f56a24e446c43e4c154 span_id=c1b44be0f1aeb260 trace_flags=01
2026-09-26T21:59:53+00:00  2026-09-26 21:59:53 - oteldemo.AdService - no baggage found in context trace_id=1ec53b69ce2d32e635be2adb3eeb3e3c span_id=aef530b1ded806f3 trace_flags=01
2026-09-26T21:59:53+00:00  2026-09-26 21:59:53 - oteldemo.AdService - Non-targeted ad request received, preparing random response. trace_id=1ec53b69ce2d32e635be2adb3eeb3e3c span_id=aef530b1ded806f3 trace_flags=01
2026-09-26T22:00:07+00:00  2026-09-26 22:00:07 - oteldemo.AdService - no baggage found in context trace_id=25752fadf153ca38533f30769868d76d span_id=f3bfbc4089ee8fde trace_flags=01
2026-09-26T22:00:07+00:00  2026-09-26 22:00:07 - oteldemo.AdService - Targeted ad request received for [telescopes] trace_id=25752fadf153ca38533f30769868d76d span_id=f3bfbc4089ee8fde trace_flags=01
2026-09-26T22:00:09+00:00  2026-09-26 22:00:09 - oteldemo.AdService - no baggage found in context trace_id=a9f8aa091cbebc24811cca66821eff93 span_id=6d530def20d9c76b trace_flags=01
2026-09-26T22:00:09+00:00  2026-09-26 22:00:09 - oteldemo.AdService - Targeted ad request received for [books] trace_id=a9f8aa091cbebc24811cca66821eff93 span_id=6d530def20d9c76b trace_flags=01
```

_488 further lines are in the bundle._

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

The page was one alert, `ServiceHighErrorRate` on **ad**, 10m31s after the trouble started.
Nothing else fired, then or later, and nothing fired after the fix.

It was slow to come because the error ratio hovered around the line. Ad's ratio had been zero. It
rose to 2-3% over the first five minutes, touched 5.0% at about six minutes, fell back under at
seven, which restarted the alert's two-minute hold, and then stayed over from between eight and nine
minutes, at 5% to 9%, until it fired. Ad's request rate and latency did not change.

Around it, almost nothing moved. The frontend's and frontend-proxy's error ratios rose to about 1%,
far under the line, and no latency changed anywhere. The storefront worked; now and then a page's
ads failed to load.

### What was checked

**Ad's log, the service on the page.** For every request it logged `Targeted ad request received for
[...]` or `Non-targeted ad request received`, and now and then, straight after, `GetAds Failed with
status Status{code=UNAVAILABLE, description=null, cause=null}`. Counted over the whole incident,
22 of about 200 requests failed, about one in ten, 0 to 4 a minute, with none before the change
and none after the fix. The failures fell on every kind of request, targeted and not, for every
category. Nothing distinguished the requests that failed from the ones that did not.

**The traces.** A failing request ended at ad's own `oteldemo.AdService/GetAds` span, in error,
under the frontend's call to it and the storefront's `/api/data`. The span carries no status
message. The error had no description to give: `UNAVAILABLE` with nothing after it. Ad had chosen
the ads, in the same few milliseconds as a request that succeeded, and then failed.

**The frontend.** Its log carried the same thing from the other side, `Error: 14 UNAVAILABLE:` with
empty details, once for each of ad's failures. The frontend was only passing on what ad told it.

**Whether ad was unwell.** It was not. Its request rate held, its latency moved no more than it had
before the change, its JVM runtime series reported without a gap, and it restarted nothing. A
service that is overloaded or failing on a dependency fails more as load rises, or fails the
requests that touch the broken dependency. This one failed a steady tenth of everything, at random,
fast, and told nobody why.

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
restarted or redeployed. The failures stopped at once, ad's error ratio drained with its window, and
the alert cleared 1m00s after the fix. Nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

### Detection notes

- Onset to first page: **10m31s**, most of it the ratio hovering at the line and restarting the
  alert's hold once. Services on the page: **one**, ad, the service the flag acts on. By the fix:
  **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one.
- Would the page alone have led you to the right service? **Yes, but not to the cause.** Ad's log
  and spans say that requests fail and never why.
- **A failure with no reason is a clue of its own.** `UNAVAILABLE` with no description, from a
  service that is up and fast and unstrained, is not what a real outage looks like.
- **A fixed random fraction is a decision, not a degradation.** One request in ten, spread over every
  kind of request and steady through the incident, is something choosing to fail. With nothing in
  change history, look for the switch that could choose it.
- **A marginal page is slow.** A fault that holds a service near the alert's line may take several
  windows to page, and can drop under and restart the hold. The time to page says little about how
  bad the fault is.

---

Rendered from [`evals/scenarios/artifacts/dev/v2-ad-flag-failure/`](../../evals/scenarios/artifacts/dev/v2-ad-flag-failure/) by `faultline-render`. [All bundles](README.md).
