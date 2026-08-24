# T2.1 evidence — what Alertmanager actually delivers

Measured, not assumed. A listener on `host.docker.internal:8000` captured every webhook
delivery Alertmanager made during one live `cart-redis-misconfig` injection, and
`payloads.jsonl` is the unedited result: **8 deliveries**, one JSON object per line.

| | |
|---|---|
| scenario | `cart-redis-misconfig` (bad_config, **dev** split) |
| injected | ~10:32Z, 2026-08-24 |
| reverted | ~10:37Z (300s hold) |
| receiver | `compose/prometheus/alertmanager.yml` → `http://host.docker.internal:8000/api/v1/alerts` |
| Alertmanager | 0.27.0, webhook payload `version: "4"` |
| routing | `group_by: [alertname, service_name]`, `group_wait: 10s`, `group_interval: 30s`, `repeat_interval: 1h` |

Each line wraps the delivery in a capture envelope — `received_at`, `path`, `headers`,
`body`. Only `body` is Alertmanager's; the other three are the listener's record of the
transport. Read the file with one object per line, not as a single JSON document.

## What one delivery contains

**Envelope, from the listener.** `received_at` (the listener's clock, microsecond
precision), `path`, and `headers`. The headers are `Host`, `Content-Length`,
`Content-Type: application/json`, and `User-Agent: Alertmanager/0.27.0`. **There is no
authentication, signature or shared-secret header** — anything that can reach the port can
post an alert, which is a fact for T2.1's trust boundary rather than an Alertmanager defect.

**Body, from Alertmanager.** Ten fields, identical in shape across all 8 deliveries:
`receiver`, `status`, `alerts`, `groupLabels`, `commonLabels`, `commonAnnotations`,
`externalURL`, `version`, `groupKey`, `truncatedAlerts`. `truncatedAlerts` was `0` on
every delivery.

**Each alert object carries seven fields, and no others:**

| Field | Measured content |
|---|---|
| `status` | `firing` or `resolved` |
| `labels` | `alertname`, `service_name`, `severity`, `signal` — the rule's labels plus the grouping ones |
| `annotations` | `summary` and `description`, both **rendered** — the description carries the live value, e.g. `frontend is failing 29.25% of calls (baseline 0%).` |
| `startsAt` | RFC3339 with milliseconds, e.g. `2026-08-24T10:34:30.583Z` |
| `endsAt` | `0001-01-01T00:00:00Z` while firing — Go's zero time, a sentinel and not a date. A real timestamp once resolved. |
| `generatorURL` | Prometheus graph link with the full rule expression URL-encoded |
| `fingerprint` | 16 hex characters, e.g. `0eeee852e85422ff` |

Two things in there are container-internal and not reachable from the host:
`generatorURL` names the Prometheus container (`http://0345b24dba28:9090/...`) and
`externalURL` names the Alertmanager container (`http://1a9e6cfeb2bd:9093`). Anything that
renders these as links for a human needs to rewrite the host part.

## Alertmanager supplies the fingerprint, and it is stable

This is the question the capture was taken to answer. `docs/evidence/gate-1/README.md`
names fingerprint dedupe as T2.1's job without saying where the fingerprint comes from.

**It comes from Alertmanager, and we do not need to compute our own.** Measured across the
four alerts in this capture, each of which was delivered twice — once firing, once resolved:

| service | fingerprint | firing | resolved |
|---|---|---|---|
| frontend | `0eeee852e85422ff` | #1 | #6 |
| loadgenerator | `7f55ecd578853462` | #2 | #7 |
| checkoutservice | `13d86469efcf3ccc` | #3 | #4 |
| emailservice | `c1cf16569b44acd6` | #5 | #8 |

Three properties fall out of that table, all measured here rather than read from
documentation:

- **Stable across the lifecycle.** The resolved delivery repeats the firing delivery's
  fingerprint exactly. It identifies the alert, not the notification.
- **Distinct per label set.** Four alerts differing only in `service_name` produced four
  different fingerprints.
- **Independent of annotations.** `frontend`'s description said `29.25%` when firing and
  `10.08%` when resolved; the fingerprint did not move. Whatever it hashes, it is not the
  rendered text — so a value that drifts between deliveries cannot split one alert into two.

`startsAt` is also stable across both deliveries of an alert (frontend: `10:34:30.583Z` in
#1 and #6), so `(fingerprint, startsAt)` names one *episode* of an alert, where
`fingerprint` alone names the alert across all of its episodes. The capture contains no
case of a fingerprint recurring with a new `startsAt`, so that distinction is reasoned from
field stability rather than observed.

## One alert per POST — a consequence of our own config, not of Alertmanager

**All 8 deliveries carried exactly one alert.** That is not how Alertmanager behaves in
general; it is what `group_by: [alertname, service_name]` produces. The grouping key is as
fine as the alerts themselves, so every group holds exactly one, and each `groupKey` in the
capture reads like `{}:{alertname="ServiceHighErrorRate", service_name="frontend"}`.

So ingest sees **a stream of single-alert notifications**, and `alerts` being a list is
currently a formality. **A change to `group_by` would change that shape** — dropping
`service_name`, for instance, would deliver one payload holding all four services at once.
T2.1 should not be written as though `alerts[0]` were the alert; the list is real, and the
config that flattens it lives in a file we edit.

## The delivery timeline

Injection ~10:32Z, revert ~10:37Z. Lag is `received_at` minus the alert's own
`startsAt`/`endsAt`.

| # | received (Z) | status | service | alert timestamp | lag |
|---|---|---|---|---|---|
| 1 | 10:34:40.651 | firing | frontend | starts 10:34:30.583 | 10.1s |
| 2 | 10:34:40.653 | firing | loadgenerator | starts 10:34:30.583 | 10.1s |
| 3 | 10:34:55.641 | firing | checkoutservice | starts 10:34:45.583 | 10.1s |
| 4 | 10:39:25.632 | resolved | checkoutservice | ends 10:39:00.583 | 25.0s |
| 5 | 10:39:40.614 | **firing** | **emailservice** | starts 10:39:30.583 | 10.0s |
| 6 | 10:39:40.626 | resolved | frontend | ends 10:39:30.583 | 10.0s |
| 7 | 10:40:10.630 | resolved | loadgenerator | ends 10:39:45.583 | 25.0s |
| 8 | 10:40:40.613 | resolved | emailservice | ends 10:40:15.583 | 25.0s |

Deliveries #1 and #2 arrived **1.5ms apart** — separate POSTs, separate groups, one flush.
Anything that batches by arrival time will see them as simultaneous and must not assume
that means they came in one request.

Lag falls into two clusters, ~10s and ~25s, against `group_wait: 10s` and
`group_interval: 30s`. The 10s cases are group_wait on a group's first notification; the
25s cases land on a later flush tick for a group that had already notified. That reading is
consistent with the config but is inferred from one capture, and nothing below depends on
it. **What is measured is the range: 10–25 seconds from alert timestamp to delivery.**

## emailservice fired after the revert, interleaved with resolutions

Delivery #5 is the one worth reading twice. `emailservice` began firing at
`startsAt 10:39:30.583`, which with `for: 2m` puts the underlying condition crossing 5%
at about **10:37:30 — essentially the moment of the revert**, not during the fault.

It arrived **12 milliseconds before** `frontend`'s resolution (#6), and its own resolution
(#8) came last of all, a minute after the incident's other alerts had cleared.

So the recovery churn produced a real alert, and at the transport layer it is
indistinguishable from the incident's opening alerts: same rule, same shape, same
`status: firing`, a fresh fingerprint the receiver has never seen. **Nothing in the payload
marks it as an artifact of recovery.** The only signal available is temporal — it starts
after other alerts of the same incident have begun resolving.

This is the shape of a real incident, not a curiosity of ours: recovery actions cause
transient failures, and they arrive as new alerts.

## ServiceNoTraffic never fired, and could not have

Only `ServiceHighErrorRate` appears in the capture. `ServiceNoTraffic` needs its `[3m]`
zero-rate window to empty **and then** its `for: 3m` to elapse — roughly six minutes of
continuous silence from a service that was previously serving. The fault was held for
**300 seconds**. The rule could not have matured inside the hold regardless of what
cartservice did.

**So this capture is one incident shape, not the repertoire.** Every conclusion here is
drawn from `ServiceHighErrorRate` deliveries only. A longer hold, or a scenario that takes
a service fully dark, would exercise a rule with different labels (`signal: availability`)
and a different lifecycle, and neither is represented here.

## No duplicates, no retries

Eight deliveries, eight distinct `(fingerprint, status)` pairs: four alerts, each delivered
once firing and once resolved. No alert was delivered twice in the same state, and the
listener recorded no retry.

**`repeat_interval: 1h` is untested.** The whole capture spans six minutes, so no alert
stayed firing long enough to be re-notified. Whether a repeat arrives byte-identical to the
original — same fingerprint, same `startsAt`, unchanged `status: firing` — is unknown from
this evidence, and it is the case most likely to look like a duplicate to a naive receiver.

## What this capture does not exercise

Stated so nobody builds on it further than it reaches:

- **Retries against a down receiver.** The listener was up for the whole window. How
  Alertmanager behaves when the POST fails — how often it retries, for how long, whether
  the retried body is identical — is unmeasured.
- **Repeat notifications.** See above: `repeat_interval` never elapsed.
- **Grouped multi-alert payloads.** Every `alerts` list had length 1, so nothing here shows
  how a multi-alert delivery orders its members, or what `commonLabels` reduces to when the
  group is heterogeneous. `truncatedAlerts` was `0` throughout, so the truncation path is
  equally untouched.
- **Any rule other than `ServiceHighErrorRate`**, and any non-`critical` severity.
- **Malformed or hostile input.** Everything captured was well-formed and came from
  Alertmanager. The port has no authentication.

## Two consequences for T2.1

Design decisions belong to T2.1 itself. These are the two constraints the measurement puts
on it, and they are constraints rather than proposals.

**1. Dedupe keys on alert identity per delivery, not on unpacking batches.** The
fingerprint is supplied, stable across an alert's lifecycle, and independent of the
annotation values that change between deliveries — so it is a usable identity and we do not
compute our own. But the deduplication unit is *an alert*, not *a POST*: one alert per
delivery is our `group_by`'s doing, not a property of the protocol, and a grouping change
would put several alerts behind one HTTP request without warning. Ingest should iterate
`alerts` and identify each element on its own terms.

**2. Resolution handling must tolerate a new firing arriving mid-resolution.** The
`emailservice` alert fired after the revert, 12ms before another alert of the same incident
resolved, and resolved last. Any logic that treats the first `resolved` as the end of an
incident, or that assumes firing and resolved deliveries arrive in tidy phases, will either
close the incident early or file the recovery artifact as a second incident. Neither is
what happened: it is one incident, and its alert stream interleaves.

## Reproducing

The listener was a plain HTTP server appending `{received_at, path, headers, body}` per
request; anything that does that works. Alertmanager already points at
`host.docker.internal:8000` in `compose/prometheus/alertmanager.yml`, so a capture needs
only a listener on that port and an injection. Note that a rehearsal recorder run will
also fire these alerts — this capture was taken alongside a normal injection, not from a
special mode.
