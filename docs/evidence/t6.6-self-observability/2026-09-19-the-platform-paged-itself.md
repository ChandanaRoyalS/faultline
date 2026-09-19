# The platform paged itself — 2026-09-19

**Four incidents about a service called `faultline`, three investigations, two of them failed,
$0.69, in thirty-two minutes on the VM, with nothing injected and nobody watching.** Q77's exposure
- *the world's alerting can page about the platform, which the receiver could one day turn into
an incident about itself* - was not a possibility when that row was written on the 18th and closed
on the 19th. It had already happened, between 15:43 and 17:00 UTC on the 19th, five hours before
the fix was applied at 19:57. Found the same evening, reading the Loki panel to close T6.6's row.

## The loop, from the incident table

| UTC | alert (service, severity) | incident | what the platform did |
|---|---|---|---|
| 15:43:15 | `ServiceHighLatency` loadgenerator, warning | `2261400b` opened | triage **gated it as noise** (exit 5). Triage is a model call; since T6.6 a model call is a span; through the collector's `spanmetrics` a span is a call for a service named `faultline` |
| 15:58:15 | **`ServiceNoTraffic` faultline, critical** (+ loadgenerator latency) | `5b1a7e7d` opened | the platform had been quiet for fifteen minutes. Investigation `f839e1ba`: ten steps, **no verdict** (exit 4), incident `failed`, $0.14 |
| 16:00:30 | `ServiceNoTraffic` faultline resolves | | the investigation's own spans were the traffic |
| 16:03:30 | **`ServiceHighLatency` faultline, warning** | `786a73ab` opened | a model call is 15-60 s, which is high latency for a service. Investigation `070ca781` **failed at its first step** - `retrieval`, payload `{}`, zero tokens (exit 4); cause not established - no ERROR-level JSON line was written by either failed run |
| 16:08:00 | `ServiceNoTraffic` faultline, critical | attached to `786a73ab` | resolved thirty seconds later; the incident resolved with it |
| 16:15:00 | `ServiceNoTraffic` faultline, critical | `acf4fc2a` opened | investigation `22f87df6` ran to a verdict, **flagged** (exit 2), $0.55 - see below |
| 16:20-16:39 | `ServiceHighLatency` faultline; then emailservice, checkoutservice, frontend (warnings) | attached to `acf4fc2a` | the world's own blips, joined to the open incident |
| 16:26:30-17:00:30 | `ServiceNoTraffic` faultline, critical | attached to `acf4fc2a` | **the loop starves**: no investigation running, no spans, the series goes stale, and a stale series cannot fire. `acf4fc2a` resolves |
| 19:57 | | | Q77 applied: the daemons export to Tempo directly; `calls_total{service_name="faultline"}` reads 0 series |

The 18th's `ServiceNoTraffic faultline` at 12:24 did not do this only because `f485a080` was open
and the alert was joined to it. The first time the platform went quiet with no incident open, it
opened one about itself.

## What the agent said when asked to investigate `faultline`

`22f87df6`'s verdict carries the flag twice: *"planner produced no valid findings: dispatch service
'faultline' is not a service this system knows. Legal values: accountingservice, adservice, …"* -
the catalog refused the dispatch, which is the right refusal (`context/catalog.py`), and the run
went on with what it could reach. Its proposal abstained, correctly, and its risk paragraph is the
platform describing its own condition without knowing it: *"the only targets in the blast radius
are 'faultline' (not a real service in this topology, so no action can be executed against it)"*.
The catalog held; the kill switch was not needed; nothing could have been executed. The cost was
the investigations and the two `failed` rows on the deployment's record, which are its first.

## What this was, in one sentence

**T6.6 made the platform observable by the world's collector, and the world's collector made it a
service the world's rules could page about, and the platform's receiver turned the page into an
incident whose investigation produced exactly the signal that resolved the alert and set up the
next one.** Every part behaved as designed. The design had a loop in it, and the loop needed only
an idle platform and a quiet world to start. Q77's closing note called this *"one day"*; it was
that afternoon.

## What this changes in the record

- **Q77's closing text said** *"it did not open an incident about itself today"* about the 18th;
  true of the 18th, and the row now says what the 19th did.
- **The deployment's `/metrics`** reads `faultline_investigations_total{outcome="failed"} = 2`.
  Both are this loop. A reader of the self dashboard should know the two failures are the
  platform investigating itself, not the world.
- **ADR-0030 addendum 4** was written as a decision about an exposure; it was a fix for a
  running defect, and it says so now.
- **No re-run, no cleanup.** The four incidents and three trajectories stay as they are: the
  record of what the deployment did unattended is the point of a deployment.

## What it does not change

The fix is the one already applied and verified: with the platform's spans going straight to
Tempo, there is no `faultline` series for a rule to read, and the loop has no first step. The
catalog's refusal of an unknown dispatch service held throughout. The world's rules are untouched
(digest-locked, and correct - a service with no traffic *should* page). What remains open is
Q76's ten-minute window, which is unrelated, and the two failed runs' causes, which the JSON logs
did not carry: a run that raises writes its traceback to stderr as plain text, which `| json`
filters out - noted, not chased.
