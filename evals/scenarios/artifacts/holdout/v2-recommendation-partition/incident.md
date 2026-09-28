---
origin: scenario:v2-recommendation-partition
split: holdout
fault_class: network_partition
recorded_from: 2026-09-28T11:46:36+00:00
capability: cap:91279a09
onset_to_page: 6m46s
page_to_fix: 5m00s
fix_to_all_clear: 6m01s
---

# The recommendation service is cut from the network - its process runs and reaches nothing

## What was observed

The page came 6m46s after the first request hung, and it was thin: `ServiceHighLatency` on
**frontend-proxy** and on **load-generator**, nothing else. Neither is a service anyone would fix;
both were reporting what they received from below them. A minute later `ServiceNoTraffic` on
**recommendation**. Three alerts on three services by the fix; four more in the minutes after
it, on the **frontend** and on recommendation, error rate and then latency; the world all clear
6m01s after the fix.

The storefront was mostly fine. Product pages, carts and checkouts served at their usual speed
and 75 orders completed while the fault held. The frontend recorded no errors and no change in
latency for the length of the fault, a p95 of 45 to 71ms, its request rate easing from 12.2 a
second to about 8.0 as some users waited. At the edge, the proxy's and the load generator's 95th
percentiles went to the histogram's ceiling, **15000ms**, from T+3 and stayed there, while their
error ratios climbed only to 4.2% and 4.5% and never reached their 5% line. Something was
hanging a small share of requests to the fifteen-second route timeout: enough to hold a 95th
percentile, not enough to hold an error rate.

Recommendation's request rate went from 0.7 a second to nothing by T+4, and from then until the
fix it had no error ratio and no latency value at all: no samples, not zero errors. The catalog's
rate halved with it, from 5.2 requests a second to about 2.3, with no errors and no change in
latency: something that used to call it had stopped calling.

## What was checked

**The proxy and the load generator, because they paged.** Their error traces - 121 in twelve
minutes, none under fourteen seconds - were all one thing: `user_get_recommendations`, a GET of
`/api/recommendations`, cut at the proxy's fifteen-second route timeout. Not one product page,
cart view or checkout among them.

**The frontend, from the traces.** Under every timed-out proxy span the frontend's
`GET /api/recommendations` was still open - for 203, 471 and 706 seconds in the three drawn - on
a single call, `grpc.oteldemo.RecommendationService/ListRecommendations`, with nothing beneath
it while the fault held. The frontend recorded no error because it had not finished; it was
waiting, with no deadline of its own, on the one service that lists recommendations.

**The catalog, because its rate had halved.** Nothing was wrong with it: zero errors, its usual
latency, every call that reached it answered. Half of its calls at rest come from
recommendation, which lists the catalog on every request it serves - and recommendation was
serving nothing. The catalog's drop was a shadow of recommendation's silence, not a fault of its
own.

**Recommendation's own view of itself.** Its 20 runtime series - memory, threads, garbage
collection - had stopped at the onset: the last report is the one before it, they held for the
store's lookback and dropped out of queries at T+4, and nothing replaced them until 14 seconds
after the fix. A service that is merely uncalled keeps sending its runtime reports on a timer.
This one had stopped reporting on itself.

**Recommendation's log.** At rest it writes one line per request, about two a minute, `Receive
ListRecommendations`. The last of those came five seconds before the onset, and then no more.
What replaced them was its telemetry SDK, writing at ERROR to the same console: `Failed to
export metrics to otel-collector:4317` 28 seconds in, and then the same line once every seventy
seconds for as long as the fault held - its export interval plus a ten-second timeout - with
`Failed to export traces` twice, when it had a batch of spans to send. Eleven lines, one per
failure, no stack traces; every one of them the fault's, none in the five minutes before it. It
was running. It was trying to send on schedule. Nothing it sent had anywhere to go, and nothing
sent to it arrived.

**What changed.** Nothing. No deploy, no image, no configuration, no limit, no flag, on any
service involved. The change history for the window is empty.

## Root cause

The recommendation container was disconnected from the demo network. The process kept running
and its port stayed open, on an address nothing could reach; packets on its established
connections were dropped rather than refused, so its one caller waited on a socket that would
never answer. Only the frontend calls recommendation, once per recommendations request and with
no deadline, so every recommendations request hung until the proxy cut it at fifteen seconds -
about one request in twenty-five on this load, which put the edge's latency over its line and
its error ratio under. Recommendation's own call into the catalog, made on every request, hung
the same way from its side, and the catalog lost half its traffic without losing anything else.
Everything else the storefront does ran as before. Recommendation itself was alive the whole
time and said so in the only place it could still write, its own log: its request lines stopped
and its export failures began within the same half minute. Nothing about it had been changed.

## Resolution

The container was put back on its network under its original names, on the same address. Where
an operator cannot reconnect a container with its aliases, recreating or restarting it does the
same job. Class of fix: **restart**. Nothing was deployed or misconfigured, so there was nothing
to roll back or revert.

The recovery was not clean, and it was not the fault. The requests the frontend had held open
through the cut did not complete when recommendation came back; they failed together, 126
frontend error lines in the minute after the fix, the frontend's error ratio at 17.5% and its
p95 at the ceiling for four minutes as the held spans closed at their minutes-long lengths.
Recommendation's own connections into the catalog, held open through the cut, were reset when
it returned - `Connection reset by peer`, its log carrying the tracebacks - and for the first
thirty seconds its flag lookups into flagd timed out at their 500ms deadline on a connection that
had gone stale, so its error ratio read 35% and its p95 770ms in the minute after the fix,
falling away over four. Four alerts fired only in this window - error rate on the frontend and
recommendation, then latency on both - and cleared as the wave passed. The no-traffic alert
cleared 29 seconds after the fix, the edge's latency alerts 3m29s after, and the world was all
clear 6m01s after the fix. Neither recommendation nor the catalog restarted.

## Detection notes

- Onset to first page: **6m46s**, the edge's 95th percentile holding the ceiling for three
  minutes once enough fifteen-second spans were in its window. Slow, because the hung share was
  small.
- Services on the page: **two**, the culprit not among them. By the fix: **three alerts across
  three services**, the culprit named once, as silence, a minute after the page.
- Alerts that fired only during recovery: **four** - the held requests failing together, on the
  frontend and on recommendation, as errors and then as latency.
- Did the loudest service turn out to be the culprit? **No.** The proxy and the load generator
  paged and stayed loudest; they were reporting what they received.
- Would the page alone have led you to the right service? **Not on its own.** The page named the
  edge; the no-traffic alert a minute later named recommendation, but a service that has gone
  quiet is also what a service nobody is calling looks like. The traces said the calls into
  recommendation never returned; the runtime reports said it had stopped reporting on itself;
  the log said why.
- **A page can be under the error line and over the latency line.** One request in twenty-five
  at fifteen seconds is 3 to 4% of requests - under an error rate, more than enough to hold a
  95th percentile at the ceiling. Read the latency alerts for what they contain.
- **A halved rate on a healthy service points at its caller.** The catalog lost half its traffic
  with no error and no latency of its own; the half it lost was recommendation's. A rate that
  falls without anything else moving is a shadow, and the thing casting it is the one to find.
- **The runtime reports separate stopped from uncalled. The log separates stopped from cut
  off.** A frozen process writes nothing; a crashed one writes a start-up; a cut-off one keeps
  writing that it cannot reach anything, on its export schedule, naming the collector it cannot
  reach.
- **The recovery's errors are the recovery's.** Held requests that fail when the connection
  returns, and stale connections to dependencies that fail until they are remade, put errors and
  latency on the culprit and its caller in the minutes after the fix that neither had during the
  fault. Errors that begin at the fix are not a second fault.
