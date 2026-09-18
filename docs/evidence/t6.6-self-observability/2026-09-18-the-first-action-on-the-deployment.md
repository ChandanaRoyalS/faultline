# The first action on the deployment — 2026-09-18

**One injected fault, two investigations, one operator rejection, one approval, one execution,
one `action.execute` span** — the first action the VM has ever performed on its own world, and the
seventh seam of T6.6 seen live. **$1.32** (two investigations: $0.624 and $0.695, priced at the
harness's table from the trajectory tables), under the $1.50 ceiling written down before the
inject. Nothing was re-run.

```
action.execute  ROOT  executor  780ms
  caller=faultline incident_id=f485a080-56ba-4eef-ade7-bb2358ceb6a3 action_id=restart_service
  target=cartservice outcome=executed token_id=7c79d90c5225224a
  audit_id=bbaee750-6064-45d1-8360-57691d3eb9dc exit_code=0
```

No `token`, no `reason`, no `command`, no `output` - asserted by the read, not assumed.

## What was written down first

Stated in the working session before the inject, so that the record can say so: `cart-redis-misconfig`
(§3.6's own scenario; its recorded proposal `revert_config → cartservice` recovered in the T6.2
replay); one live investigation; approval through the API's approve route, which presents the
token to the executor *container*; expected an incident in `awaiting_approval` within ~8 minutes,
`executed` with exit 0, exactly one Tempo trace with `resource.faultline.component="executor"`
whose root is `action.execute` carrying the audit row's structural fields and no token, a trace id
different from the investigation's, alerts clearing inside `confirm_within_seconds`, and
`faultline-inject stop --all` reverting nothing. Ceiling $1.50. *"A different proposal from the
agent is not a failure of any of this - it is the run."*

Of those: the state was `proposing`, not `awaiting_approval` - that is where a proposal rests
and the approval itself moves it; the first proposal abstained; the alerts did not clear on the
action; `stop --all` reverted the fault; and Tempo held the span and could not serve it for
twenty minutes. Each below.

## The run, in the order it happened (UTC)

| when | what |
|---|---|
| 11:49:26 | `faultline-inject start cart-redis-misconfig` - cartservice recreated with `REDIS_ADDR=redis-cart:6380` |
| 11:52:25 | incident `f485a080` opened, **critical** (`ServiceHighErrorRate` on frontend, checkoutservice, loadgenerator) |
| 11:54:04 | trajectory `18b09ed5` starts; trace `fbafd1bf862afca3c648b028432ddd20`; every orchestrator log line of the run carries that `trace_id` - **the log-to-trace join, live on the VM for the first time** |
| ~11:58 | `triaging → planning → investigating → synthesizing → proposing`. Root cause names cartservice from trace shape alone and says of itself *"no dispatch ever queried cartservice's logs, metrics, resources, or change history"*. **Proposal: abstain** (`remediation_class=none`): *"The next step is measurement, not remediation."* |
| 12:07:48 | `POST …/reject` with the reason below. State `rejected` |
| 12:07:59 | trajectory `7db34bbd` starts on the orchestrator's next poll - no triage gate on re-entry (ADR-0039 addendum); trace `d6253cecb94c8fa53da55a0cc5f0a669`; the reason is in the brief (`re-investigating after an operator rejection: …`) |
| ~12:12 | `rejected → planning → investigating → synthesizing → proposing`. Root cause: GetCart is the terminal hop in all 15 error traces, client self-time only, *"no cartservice server span or Redis HGET child beneath it"*, change points 11:50:15 / 11:50:30, no change on the calling side. **Proposal: `restart_service → cartservice`**, confirm within 300 s |
| 12:15:18 | `POST …/acknowledge` (critical needs one), then `POST …/approve`: token `7c79d90c5225224a` minted, caller `faultline` (the credential's username, not a constant) |
| 12:15:19.49 | executor: `action.execute` opens |
| 12:15:20.27 | executor: **executed**, exit 0, audit `bbaee750`; span closes after 780 ms |
| 12:24:57 | alerts still firing - and more of them: `ServiceNoTraffic` on eight services, **`faultline` among them**. Incident `executing` |
| 12:25:0x | `faultline-inject stop --all` → `reverted cart-redis-misconfig` |
| 12:26 | one alert left: `ServiceNoTraffic faultline` |
| ~12:35 | no active alerts; incident **`resolved`** |

**The rejection reason, verbatim** (it went into the agent's brief and into `incident_rejections`):
*"Abstention rejected. Your own synthesis says no dispatch ever queried cartservice, yet it names
cartservice as the failing component. Investigate cartservice directly - its change history,
configuration and logs over the incident window - and propose an action or abstain on evidence
about it."* It points at where to look and not at the answer; a reason that said *the Redis
address is wrong* would have been the operator proposing and the agent transcribing.

## What the action did, and did not do

**The restart did not fix the fault, and could not have.** `restart_service` recreates cartservice
from the compose files the injector's override is still part of, so the container came back with
the same wrong `REDIS_ADDR`. The alerts cleared only after `stop --all` removed the override at
12:25, and the incident resolved on that. This is the same shape as the T6.2 replay's one
`not-recovered` row (`redis-cart-dependency-latency`, also `restart_service`), and it is the
agent's second proposal being wrong about the mechanism while right about the component: the
synthesis saw no HGET child beneath GetCart and read *unresponsive*, where the truth was *talking
to a Redis that is not there*. A `revert_config` - the recorded proposal from dev sweep 12 - would
have recovered it, as the replay showed. **Recorded as it happened; no re-run to get the better
proposal.**

**Eight `ServiceNoTraffic` alerts at 12:24:57.** Whether the restart or thirty-five minutes of a
broken cart caused the load generator's orders to stop reaching shipping, quote, accounting,
currency, email and frauddetection is not established; they cleared with the fault.

**One of them was about the platform.** `ServiceNoTraffic faultline`: the platform's own spans go
through the world's collector, whose `spanmetrics` processor turns every `service.name` into
`calls_total{service_name=…}`, and the world's rules alert on a service that goes quiet - which
`faultline` did, between investigations. So the platform's traces have made it a service in the
world's metrics, visible to the agent's `promql_query` (the exposure Q73 closed `/metrics` against,
open again by another door) and to the world's alerting. It did not open an incident about itself
today. **Q77.**

## The span: in two backends, and invisible in one for twenty minutes

The approve route posts the token to `http://executor:8100/execute`; the executor's access log
shows the POST at 12:15:20.273; the audit row is written at 12:15:20.270. The span should have
followed within five seconds. **Tempo search found nothing at 12:19, 12:21, 12:24 and 12:35;
`GET /api/traces/31a11694…` returned 404 at 12:37.** Jaeger - the other exporter on the same
collector pipeline - had it, with every attribute above.

Ruled out on the way, each with a $0 probe from inside the executor container: the network path
(a span flushed on exit arrived at once); the background exporter (a span with no flush, process
killed with `os._exit`, arrived); the uvicorn worker-thread path (a span opened inside a sync
endpoint under a real uvicorn server, arrived); the live daemon itself (one invalid token presented
by hand → a `refused` span with `caller=probe`, arrived in fifteen seconds - and one refusal row in
`action_audit`, `cc5e131c`, which is what that ledger is for). The collector's counters:
`otelcol_exporter_sent_spans{exporter="otlp/tempo"}` 175,992, `send_failed` 0, queue 0 - equal to
the Jaeger leg. Tempo's: `receiver_refused_spans` 0, `discarded_spans_total` 0 on every reason,
`failed_flushes_total` 0. **Tempo accepted the span and could not serve it.**

Then at 12:42:49 the same `GET` returned **200**, with nothing changed. Tempo's log between:

```
12:19:38 error poller.go:156 "failed to poll or create index for tenant" … no such file or directory
12:29:38 error poller.go:156 "failed to poll or create index for tenant" … no such file or directory
12:34:38 error poller.go:156 "failed to poll or create index for tenant" … no such file or directory
12:39:38 info  poller.go:238 "writing tenant index" metas=23 compactedMetas=128
12:39:38 info  poller.go:133 "blocklist poll complete"
```

**The mechanism.** T6.1 set `max_block_duration: 30s` and `complete_block_timeout: 2m` in
`compose/tempo.yaml` so the trace tool would see an incident within minutes rather than after the
default thirty. A trace therefore leaves the ingester about two and a half minutes after it
arrives, and from then on the querier can reach it only through the tenant's block index, which
the poller rewrites every ten minutes - and which fails whenever the compactor has removed a block
between the listing and the read, as it did at 11:59, 12:09, 12:19, 12:29 and 12:34. **Between
leaving the ingester and the next successful poll, a trace is in Tempo and invisible to it, by
search and by id.** The 12:34:39 probe span demonstrated the other half: found by search at 12:35
while in the ingester, gone from search at 12:42 after leaving it, because the 12:39:38 index was
written before its block existed. It will be back at 12:49. **Q76.**

This is the first-trace note's addendum 2 - *"search disagreed with itself … not reproduced
since"* - reproduced, with the mechanism, on the span the exercise was for.

## What this does and does not show

**Shown**: the four daemons export, and the fourth's span carries the audit's structure and none
of its secrets; the rejection loop runs on the deployment end to end from a curl; the log-to-trace
join is live; the API's approve route mints and presents without the token ever reaching a
browser or a terminal; the incident page's `trace …` link now has an action's trace to point at
as well as two investigations'.

**Not shown**: an action that fixed anything - the restart did not; a trace that joins the action
to the investigation by trace id - nothing propagates context across the HTTP hop, as Q74's
closing row said, so the join is `incident_id`; a Tempo that can be trusted to show a trace that
exists, within ten minutes of it existing.
