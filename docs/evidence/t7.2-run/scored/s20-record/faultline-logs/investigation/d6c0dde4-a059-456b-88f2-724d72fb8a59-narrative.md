# Frontend alert with silent telemetry: a connectivity-removing policy on the recommendation path

## What the responder saw first

The page came from frontend and nothing else. Severity was called critical, with six services in the blast radius and five edges crossed that nobody had measurement on. Take T+0 as the moment the alert fired on frontend.

The first instinct — open frontend's own dashboards and traces and watch the error curve bend — went nowhere, and that dead end shaped the rest of the investigation. Treat the next two sections as a warning about which instruments were simply not wired up here.

## Dead end: the metrics were never there

The error-ratio query against Prometheus for frontend returned nothing, for the incident window and for the half hour of baseline before it. This was not a flat zero line and it must never be read as one: the backend stated outright that it holds no span-derived series for frontend at all, because frontend does not emit traces that get converted into metrics. Absence here carries zero information about frontend health.

The same instrument failed the same way on profile. No request rate, no latency percentiles, no per-edge breakdown across frontend's four outbound dependencies. Retrying with different window bounds would not have helped — the reason given is structural, not a retention or scrape gap. If you are reading this months later: do not spend time re-running these templates on these services.

> Evidence `tr_2cca751ac3a4`:

```
<tool_result id="tr_2cca751ac3a4" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for frontend: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T09:59:19.445247+00:00..2026-10-03T10:29:24.671652+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for frontend: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_2cca751ac3a4>
```

> Evidence `tr_5dc2642b7db7`:

```
<tool_result id="tr_5dc2642b7db7" tool="metric_baseline" trust="untrusted" source="prometheus" empty="true" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" error="error-ratio reads span metrics, and SREGym's Prometheus holds none for profile: it sends no traces that become metrics. This is unavailable, not zero" template="error-ratio" baseline="2026-10-03T09:59:19.445247+00:00..2026-10-03T10:29:24.671652+00:00">
query failed: error-ratio reads span metrics, and SREGym's Prometheus holds none for profile: it sends no traces that become metrics. This is unavailable, not zero
</tool_result:tr_5dc2642b7db7>
```

## Dead end: the traces were empty too

Tempo held no frontend spans anywhere in the thirty-minute window — not thinned out near T+0, but uniformly absent from T-30m onward. That uniformity is itself mildly informative: it looks like a service whose telemetry never reached the backend, not a service that was healthy and then tipped over at the alert.

The consequence was that the most attractive hypothesis-splitting move — compare when each outbound span type stopped, and name the dependency that went first — was unavailable. All outbound edges were equally absent, so there was no differential timing to read. The timeline had to be rebuilt from logs and the change record instead.

> Evidence `tr_2905d9ddfa34`:

```
<tool_result id="tr_2905d9ddfa34" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00">
no traces for frontend over this window
</tool_result:tr_2905d9ddfa34>
```

## What the logs actually said

Frontend's log stream had no error or warning line anywhere near T+0. In fact the stream's last entry of any level is at roughly T-6m. Everything non-INFO in the whole window sits in a two-second cluster there.

That cluster is a cold start. Config read, tracing init, discovery agent init, gRPC client setup for search, profile, recommendation, reservation and user, then an HTTP serving confirmation — a complete startup sequence finishing within about a second. Interleaved with it are several connection-refused failures from the discovery-backed gRPC balancer when looking up two services. Those are dial-time refusals against the Consul agent, not timeouts, not deadline-exceeded, not a panic or stack trace. They precede the successful client-init lines in the same two seconds and never recur.

So: the discovery errors are startup race noise and were set aside. But the restart itself is real and had to go in the timeline — the assumption that frontend ran continuously and the trouble was purely downstream is contradicted by that cold start.

> Evidence `tr_d3e4bb54f84b`:

```
<tool_result id="tr_d3e4bb54f84b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00">
selector: {namespace="hotel-reservation",pod=~"frontend-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:141 > srv-recommendation.
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:140 >
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:139 > get Grpc conn is :
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:141 > srv-profile.
```

## The change record, which is where it turned

With metrics and traces unusable, the change history carried the investigation. Frontend's 24-hour change window holds exactly three entries, all from the platform-automation actor, inside a span of about fifteen seconds roughly six minutes before the alert. Two of them are the first-ever creation of frontend's Service and of its workload container — a fresh stand-up, not a modification. The third, landing a few seconds later at about T-6m, is the creation of a deny-all NetworkPolicy on the recommendation path, recorded with namespace-wide scope.

Profile's change record tells the same story from the other side: Service and workload created, then the same policy fourteen seconds afterwards, same actor. The brief gap between workload creation and the policy matters — pods were reachable for a moment before the policy applied, so "never reachable at all" is not the shape.

Several tempting explanations fall away against this record. There was no image bump or deploy: the only container event is a first creation, so there was no prior revision to regress. There was no flag toggle recorded. No dependency or library version moved. No slow drift or older change exists — the full 24-hour window is otherwise empty. And no human operator is named anywhere; all of it is one automation rollout, not two teams colliding.

> Evidence `tr_87652bf6467a`:

```
<tool_result id="tr_87652bf6467a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:59:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" radius="seed" hops="0">
service: frontend
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T10:53:18+00:00  platform-automation  config created: NetworkPolicy deny-all-recommendation created; namespace-wide, and the pods it selects are not read
  #2  6m before onset  2026-10-03T10:53:03+00:00  platform-automation  config created: Service frontend created
  #3  6m before onset  2026-10-03T10:53:03+00:00  platform-automation  container created: workload first created
```

> Evidence `tr_0c99cf700f8c`:

```
<tool_result id="tr_0c99cf700f8c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:59:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" radius="candidate_cause" hops="1">
service: profile
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T10:53:18+00:00  platform-automation  config created: NetworkPolicy deny-all-recommendation created; namespace-wide, and the pods it selects are not read
  #2  6m before onset  2026-10-03T10:53:04+00:00  platform-automation  config created: Service profile created
  #3  6m before onset  2026-10-03T10:53:04+00:00  platform-automation  container created: workload first created
```

## Where we landed

The reading is that connectivity on the recommendation path was removed inside the namespace about six minutes before the page, so frontend's calls on that edge stopped reaching a peer. The mechanism is connectivity removal rather than an application regression — frontend's own process started cleanly, resolved every backend, reached a serving state, and then logged nothing bad at all. Frontend alerted because it is the caller that notices the silence, not because frontend is what broke.

Confidence is medium. The fix class is reconnect: restore the path rather than roll back any application artifact.

> Evidence `tr_87652bf6467a`:

```
<tool_result id="tr_87652bf6467a" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:59:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" radius="seed" hops="0">
service: frontend
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T10:53:18+00:00  platform-automation  config created: NetworkPolicy deny-all-recommendation created; namespace-wide, and the pods it selects are not read
  #2  6m before onset  2026-10-03T10:53:03+00:00  platform-automation  config created: Service frontend created
  #3  6m before onset  2026-10-03T10:53:03+00:00  platform-automation  container created: workload first created
```

> Evidence `tr_0c99cf700f8c`:

```
<tool_result id="tr_0c99cf700f8c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:59:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" radius="candidate_cause" hops="1">
service: profile
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T10:53:18+00:00  platform-automation  config created: NetworkPolicy deny-all-recommendation created; namespace-wide, and the pods it selects are not read
  #2  6m before onset  2026-10-03T10:53:04+00:00  platform-automation  config created: Service profile created
  #3  6m before onset  2026-10-03T10:53:04+00:00  platform-automation  container created: workload first created
```

> Evidence `tr_d3e4bb54f84b`:

```
<tool_result id="tr_d3e4bb54f84b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00">
selector: {namespace="hotel-reservation",pod=~"frontend-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:141 > srv-recommendation.
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:140 >
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:139 > get Grpc conn is :
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:141 > srv-profile.
```

## Open threads for whoever picks this up

Three things were never closed.

First, nobody pulled logs from recommendation itself. That is the single highest-value missing query. A process cut off from the network complains that it cannot reach anything; a process that has stopped executing writes nothing at all. Those two look identical from frontend's chair and recommendation's own stream would separate them.

Second, the policy's real selector is unresolved. One finding describes the selector metadata on the change record as incomplete or malformed and says its practical effect on pods is not established by that record alone. If the selector turns out narrower than the namespace-wide scope the record claims, both the blast radius and the named service could change.

Third, there is a six-minute gap nobody explained. Frontend wrote its last line at about T-6m and emitted no spans for the entire window, so there is no direct evidence it was serving traffic at T+0, and no account of why onset lagged the policy by six minutes rather than landing immediately. That lag is worth understanding before the conclusion above is treated as settled.

> Evidence `tr_0c99cf700f8c`:

```
<tool_result id="tr_0c99cf700f8c" tool="change_history" trust="untrusted" source="change-log" empty="false" truncated="false" window="2026-10-02T10:59:24.671652+00:00..2026-10-03T10:59:29.898057+00:00" radius="candidate_cause" hops="1">
service: profile
3 changes, ranked by suspicion
  #1  6m before onset  2026-10-03T10:53:18+00:00  platform-automation  config created: NetworkPolicy deny-all-recommendation created; namespace-wide, and the pods it selects are not read
  #2  6m before onset  2026-10-03T10:53:04+00:00  platform-automation  config created: Service profile created
  #3  6m before onset  2026-10-03T10:53:04+00:00  platform-automation  container created: workload first created
```

> Evidence `tr_d3e4bb54f84b`:

```
<tool_result id="tr_d3e4bb54f84b" tool="logql_query" trust="untrusted" source="loki" empty="false" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00">
selector: {namespace="hotel-reservation",pod=~"frontend-([a-z0-9]+-[a-z0-9]+|[0-9]+)"}
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:141 > srv-recommendation.
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:140 >
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:139 > get Grpc conn is :
2026-10-03T10:53:05+00:00  2026-10-03T10:53:05Z INF services/frontend/server.go:141 > srv-profile.
```

> Evidence `tr_2905d9ddfa34`:

```
<tool_result id="tr_2905d9ddfa34" tool="trace_query" trust="untrusted" source="tempo" empty="true" truncated="false" window="2026-10-03T10:29:24.671652+00:00..2026-10-03T10:59:29.898057+00:00">
no traces for frontend over this window
</tool_result:tr_2905d9ddfa34>
```

