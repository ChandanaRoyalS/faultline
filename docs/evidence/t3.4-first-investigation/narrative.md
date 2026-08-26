# Checkout errors traced to a shipping dependency that never finished booting

## What was visible, in order

Take the checkoutservice page as T+0. Within about three minutes six more services alerted alongside it — loadgenerator, accounting, email, frauddetection, quote and shipping — which made this look like a broad shared-infrastructure event and widened the early search unhelpfully. Twelve services were in the blast radius and five edges were crossed without ever being measured.

The first useful check was whether checkoutservice was itself sick. Error-ratio data over a fifteen-minute window opening at T-10m came back as one continuous series with a full sample count and no gaps, peaking near 28% and touching zero somewhere inside the window. That settled three things at once: the alert was real and not a dashboard artifact, checkoutservice was still serving and reporting rather than dead, and this was not a total outage of a hard dependency, since roughly three quarters of calls still succeeded at the worst point. The zero touch also meant onset happened inside the window rather than predating it.

Traces then narrowed it sharply. In every failing checkout trace the error status appears first and only on the checkoutservice-originated ShippingService/GetQuote call, the last child of prepareOrderItemsAndShippingQuoteFromCart, with no span from the callee beneath it. From there it propagates strictly upward to PlaceOrder, then the frontend gRPC handler, then the frontend HTTP POST. Failing traces run 4–12ms end to end and the erroring span returns in 0.3–2.4ms — an immediate refusal, not an exhausted deadline.

Logs for the dependency explained the missing child span. A full unfiltered pull returned no errors, no exceptions, no stack traces — only a three-line JVM and agent startup banner repeating about thirteen times, with nothing after it. No framework init, no server bind, no business logic. Gaps between restarts widen from 5–6s through roughly 18s, 30s and 56s, then plateau near 65s: supervisor-imposed backoff, so restart frequency is not a severity signal. The service was silent for the first seven minutes of the window, then began cycling abruptly — a step change, not a ramp.

> Evidence `tr_bf1ed807067d`:

```
<tool_result id="tr_bf1ed807067d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2838 n=61
</tool_result:tr_bf1ed807067d>
```

> Evidence `tr_8657d00962e4`:

```
<tool_result id="tr_8657d00962e4" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
service: checkoutservice
200 spans
  f4d1fbc856144e40 cartservice/HGET 0.4ms
  f4d1fbc856144e40 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
  f4d1fbc856144e40 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

> Evidence `tr_2ccf8bd687ef`:

```
<tool_result id="tr_2ccf8bd687ef" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
selector: {service="shipping-service"}
2026-08-26T01:39:30.360598+00:00  [otel.javaagent 2026-08-26 01:39:30:360 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-08-26T01:39:34.977124+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-26T01:39:35.282228+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-26T01:39:35.400564+00:00  [otel.javaagent 2026-08-26 01:39:35:400 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
```

## Dead ends worth keeping

currencyservice sits on the checkout path and appears in nearly every failing trace, sometimes twice. Every one of those spans is clean and sub-millisecond. Adjacent to the error, not its source.

paymentservice appears nowhere in the 200 sampled spans — checkout aborts during cart and quote preparation, so payment is never reached. Chasing declined charges is chasing a stage the requests never got to. The frontend errors only as an ancestor and adds about a millisecond. cartservice with its Redis HGET, productcatalogservice and occasional featureflagservice calls all complete without error at low single-digit milliseconds.

An application-level exception inside the quote handler was the most natural hypothesis and is wrong: the process never logs past the agent banner, so no handler code appears to run. For the same reason a code change to that handler does not fit — death happens too early in the lifecycle. That does not clear a change to the image, entrypoint, JVM flags or agent configuration. Also resist writing that the dependency was 'up and returning gRPC errors'; it returned nothing, and callers hit an absent endpoint.

The change-history result is the most misleading artifact in this record. It came back empty and it is tempting to read that as 'nothing changed.' It targeted quoteservice, not shippingservice, and covered only T-10m to T+5m. It legitimately clears a quoteservice deploy, flag flip or in-flight rollout at onset, and nothing else. No change record for shippingservice has ever been examined.

> Evidence `tr_8657d00962e4`:

```
<tool_result id="tr_8657d00962e4" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
service: checkoutservice
200 spans
  f4d1fbc856144e40 cartservice/HGET 0.4ms
  f4d1fbc856144e40 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
  f4d1fbc856144e40 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

> Evidence `tr_2ccf8bd687ef`:

```
<tool_result id="tr_2ccf8bd687ef" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
selector: {service="shipping-service"}
2026-08-26T01:39:30.360598+00:00  [otel.javaagent 2026-08-26 01:39:30:360 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-08-26T01:39:34.977124+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-26T01:39:35.282228+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-26T01:39:35.400564+00:00  [otel.javaagent 2026-08-26 01:39:35:400 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
```

> Evidence `tr_1c0655065fe4`:

```
<tool_result id="tr_1c0655065fe4" tool="change_history" trust="untrusted" source="change-log" empty="true" truncated="false" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
no changes recorded for quoteservice over this window
</tool_result:tr_1c0655065fe4>
```

## Conclusion, and what is still open

checkoutservice is not broken. Every failing checkout ends at the same leaf, and the callee is in a throttled restart loop that never binds its server, so callers get an immediate connection-level failure that rides up to the frontend. Because the process dies before any application output, the cause lives in the deployed artifact or its launch environment. Rollback of the most recent shippingservice deployment is the highest-value first move, with a configuration revert as fallback. Confidence is medium, and the medium is doing real work: the artifact story is inferred from where logging stops, not confirmed from a change record.

Open items, in priority order. First, no change history has been queried for shippingservice at all; a deploy, config and flag query covering at least the hour before onset would confirm or refute the whole conclusion. Second, what actually kills the JVM is unknown — no exit code, out-of-memory status, restart reason or runtime event was retrieved, and a wrong image tag, a missing environment variable, an unsatisfiable JVM flag and a memory limit hit at startup all produce this same signature with different fixes. Third, several things were never measured: why the dependency was silent for the window's first seven minutes (true onset, or missing collection), why checkout peaks at only 28% if the callee never boots (replica-level health was never checked, and a fallback or cached path is equally plausible), whether the six other alerting services are independent failures or downstream fallout, and what the five unmeasured edges concealed.

> Evidence `tr_8657d00962e4`:

```
<tool_result id="tr_8657d00962e4" tool="trace_query" trust="untrusted" source="jaeger" empty="false" truncated="true" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
service: checkoutservice
200 spans
  f4d1fbc856144e40 cartservice/HGET 0.4ms
  f4d1fbc856144e40 checkoutservice/hipstershop.ProductCatalogService/GetProduct 0.9ms
  f4d1fbc856144e40 productcatalogservice/hipstershop.ProductCatalogService/GetProduct 0.0ms
```

> Evidence `tr_2ccf8bd687ef`:

```
<tool_result id="tr_2ccf8bd687ef" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="true" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
selector: {service="shipping-service"}
2026-08-26T01:39:30.360598+00:00  [otel.javaagent 2026-08-26 01:39:30:360 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
2026-08-26T01:39:34.977124+00:00  Picked up JAVA_TOOL_OPTIONS: -javaagent:/app/opentelemetry-javaagent.jar
2026-08-26T01:39:35.282228+00:00  OpenJDK 64-Bit Server VM warning: Sharing is only supported for boot loader classes because bootstrap classpath has been appended
2026-08-26T01:39:35.400564+00:00  [otel.javaagent 2026-08-26 01:39:35:400 +0000] [main] INFO io.opentelemetry.javaagent.tooling.VersionLogger - opentelemetry-javaagent - version: 1.19.1
```

> Evidence `tr_bf1ed807067d`:

```
<tool_result id="tr_bf1ed807067d" tool="promql_query" trust="untrusted" source="prometheus" empty="false" truncated="false" window="2026-08-26T01:32:15.583000+00:00..2026-08-26T01:47:15.583000+00:00">
query: sum by(service_name) (rate(calls_total{service_name="checkoutservice",status_code="STATUS_CODE_ERROR"}[2m])) / sum by(service_name) (rate(calls_total{service_name="checkoutservice"}[2m]))
1 series
  {service_name=checkoutservice} min=0 max=0.2838 n=61
</tool_result:tr_bf1ed807067d>
```


