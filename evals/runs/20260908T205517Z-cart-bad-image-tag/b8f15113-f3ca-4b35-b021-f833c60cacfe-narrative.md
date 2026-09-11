# Checkout failures traced to a cart dependency that stopped serving after an image update

## What happened, in order

Alerts fired on checkoutservice, frontend and loadgenerator; the blast radius covered twelve services with four unmeasured edges. From the responder's chair the visible sequence was: cart serving normally until about four seconds before T+0; an orderly hosting-lifetime shutdown entry on cartservice at T+0 with no stack trace or fatal line; an image-reference update to a hotfix tag landing on cartservice one second later, by automation; then total cart log silence through the end of the window at roughly T+5m. Checkoutservice kept accepting requests at a steady cadence but from about T+1m30s its orders show only the entry line — the payment, email and message-write completion lines that accompanied earlier successful orders are gone. Ten of ten sampled failing checkout traces share one shape and terminate on an error-flagged leaf cart-fetch span, with near-zero self time in checkoutservice's own spans. Conclusion, high confidence: the replacement cart image took the place of a healthy process and never came back up. Fix class is rollback.

> Evidence `tr_aef3c0d8efc6`:

```
<tool_result id="tr_aef3c0d8efc6" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:28:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="cart-service"}
2026-09-08T20:28:46.903369+00:00  AddItemAsync called with userId=e4af2052-abc3-11f1-b359-b6ed2071a170, productId=2ZYFJ3GM2N, quantity=5
2026-09-08T20:28:46.905346+00:00  GetCartAsync called with userId=e4af2052-abc3-11f1-b359-b6ed2071a170
2026-09-08T20:28:46.913873+00:00  GetCartAsync called with userId=e4af2052-abc3-11f1-b359-b6ed2071a170
2026-09-08T20:28:46.931291+00:00  EmptyCartAsync called with userId=e4af2052-abc3-11f1-b359-b6ed2071a170
```

> Evidence `tr_43e2b50377c9`:

```
<tool_result id="tr_43e2b50377c9" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T20:58:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" radius="candidate_cause" hops="1">
service: cartservice
15 changes, ranked by suspicion
  #1  3m before onset  2026-09-08T20:55:22.073768+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
  #2  2.2h before onset  2026-09-08T18:46:34.411263+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_35955453bf63`:

```
<tool_result id="tr_35955453bf63" tool="trace_query" trust="untrusted" source="tempo" empty="false" truncated="false" window="2026-09-08T20:28:45.583000+00:00..2026-09-08T21:00:36.398000+00:00">
service: checkoutservice
10 trace(s) shown of 10 found, 50 spans; offsets are from each trace's root

trace 8dca6e0bdbeeddb3  root frontend/HTTP POST  7.9ms  started 2026-09-08T20:56:49.781047+00:00  5 spans
  +0.0ms frontend/HTTP POST 7.9ms [self 0.3ms]  ERROR
```

## The dead ends, which are the useful part

First, the change log for checkoutservice itself was genuinely empty over the preceding day — no deploy, config edit or flag flip, and nothing landing mid-incident. It was run at zero dependency hops, so reading it as 'nothing changed anywhere' would have cost us the answer. Second, the checkoutservice error ratio pointed the wrong way: the incident-window mean was about half the baseline mean, with only a brief late spike near T+2m, and the baseline already carried a substantial variable error fraction. No step-up at onset to anchor on. Third, checkoutservice logs never named the failing dependency — every line was severity info, with no timeout value, no endpoint string, no error at all. Fourth, cart-side error metrics returned zero samples in both the incident and baseline windows, so the absence is a mis-labelled or missing series rather than telemetry dying at onset; there is no server-side confirmation of cart errors anywhere in this record. Finally, two attractive cart-side causes died on timing: a cache-address change and an attached traffic-shaping delay were each applied and reverted hours before onset, so neither was in effect at T+0.

> Evidence `tr_d6b858e8bc87`:

```
<tool_result id="tr_d6b858e8bc87" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-09-07T20:58:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" radius="seed" hops="0">
no changes recorded for checkoutservice over this window
</tool_result:tr_d6b858e8bc87>
```

> Evidence `tr_e19a0159dcc4`:

```
<tool_result id="tr_e19a0159dcc4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T20:28:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" template="error-ratio" baseline="2026-09-08T19:56:54.768000+00:00..2026-09-08T20:28:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.07986 min=0 max=0.6667 sd=0.2155
  baseline window: n=128 mean=0.148 min=0 max=0.3091 sd=0.1245
```

> Evidence `tr_d7bc36981895`:

```
<tool_result id="tr_d7bc36981895" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-09-08T20:28:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" template="error-ratio" baseline="2026-09-08T19:56:54.768000+00:00..2026-09-08T20:28:45.583000+00:00">
service: cartservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="cartservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
  incident window: no samples
  baseline window: no samples
```

## Still open

No container or pod state was ever queried. That the new cart image failed to start is inferred from log silence alone — crash-looping, stuck image pull, failed readiness probe and never-scheduled are all consistent with what we saw, and each implies a different remedy. The change record lists the prior image value as null rather than a concrete tag, so the artifact to roll back to is not named in evidence. The pre-existing nonzero checkoutservice error fraction in the baseline is unexplained and may be a second, unrelated degradation; the earlier apply-and-revert cycles of this same hotfix are a plausible source. Only checkoutservice and cartservice were investigated out of twelve services, so nothing rules out a concurrent independent failure the cart outage is masking. And every queried window ends around T+5m, so whether cart recovered — for instance if the automation loop reverted the hotfix as it has three times before — is unknown; the incident may have self-resolved.

> Evidence `tr_43e2b50377c9`:

```
<tool_result id="tr_43e2b50377c9" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-09-07T20:58:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" radius="candidate_cause" hops="1">
service: cartservice
15 changes, ranked by suspicion
  #1  3m before onset  2026-09-08T20:55:22.073768+00:00  platform-automation  image updated: image reference updated on cartservice
      None  ->  ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2
  #2  2.2h before onset  2026-09-08T18:46:34.411263+00:00  platform-automation  environment reverted: REDIS_ADDR reverted on cartservice
```

> Evidence `tr_e19a0159dcc4`:

```
<tool_result id="tr_e19a0159dcc4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-09-08T20:28:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" template="error-ratio" baseline="2026-09-08T19:56:54.768000+00:00..2026-09-08T20:28:45.583000+00:00">
service: checkoutservice
metric: error-ratio
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
  incident window: n=128 mean=0.07986 min=0 max=0.6667 sd=0.2155
  baseline window: n=128 mean=0.148 min=0 max=0.3091 sd=0.1245
```

> Evidence `tr_161a559ef3a0`:

```
<tool_result id="tr_161a559ef3a0" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-09-08T20:28:45.583000+00:00..2026-09-08T21:00:36.398000+00:00" oldest_kept="8" newest_kept="32">
selector: {service="checkout-service"}
2026-09-08T20:28:46.912699+00:00  {"message":"[PlaceOrder] user_id=\"e4af2052-abc3-11f1-b359-b6ed2071a170\" user_currency=\"USD\"","severity":"info","timestamp":"2026-09-08T20:28:46.912589923Z"}
2026-09-08T20:28:46.929385+00:00  {"message":"payment went through (transaction_id: 6f03b87b-dceb-4b23-b66f-d4acad8bcfbf)","severity":"info","timestamp":"2026-09-08T20:28:46.929305923Z"}
2026-09-08T20:28:46.934103+00:00  {"message":"order confirmation email sent to \"larry_sergei@example.com\"","severity":"info","timestamp":"2026-09-08T20:28:46.933966881Z"}
2026-09-08T20:28:46.934846+00:00  {"message":"Successful to write message. offset: 15998","severity":"info","timestamp":"2026-09-08T20:28:46.934748881Z"}
```

