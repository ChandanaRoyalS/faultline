# T2.1 live smoke — the receiver, running, against real Alertmanager delivery

**The first successful delivery since the webhook was configured at T1.3.** Alertmanager
has been pointed at `host.docker.internal:8000` since then with nothing listening; the
capture in `docs/evidence/t2.1-webhook/` was taken by a bare recorder that logged bodies and
threw them away. This is the built receiver: eight POSTs accepted, validated, deduplicated
and published to Redis Streams, end to end.

| | |
|---|---|
| scenario | `cart-redis-misconfig` (bad_config, dev) |
| injected | ~11:08Z, 2026-08-24 |
| receiver | `faultline-ingest` → uvicorn on `0.0.0.0:8000` |
| stream | `faultline:alerts` on the platform profile's `redis` |
| first alert | 11:12:00.583Z |
| last event | 11:16:55.645Z |

## Files

- **`server.log`** — uvicorn's access log for the run.
- **`stream-events.txt`** — `redis-cli XRANGE faultline:alerts - +` after the incident
  closed. Eight entries, each three lines: stream id, the field name `event`, the JSON.

## What the run showed

**Nine requests, eight accepted.** The 422 is deliberate and came first: an empty body,
posted by hand before the injection, to confirm the validation boundary rejects a
non-delivery. Every one of Alertmanager's own eight deliveries returned 200.

```
INFO:     127.0.0.1:50448 - "POST /api/v1/alerts HTTP/1.1" 422 Unprocessable Entity
INFO:     127.0.0.1:50458 - "POST /api/v1/alerts HTTP/1.1" 200 OK
... seven more 200s
```

**Eight POSTs became eight events — no duplicates, and no losses.** `XLEN faultline:alerts`
read **3** after the firing cluster and **8** after the incident resolved. Those two readings
were taken live and are not in the committed files; what `stream-events.txt` holds is the
final `XRANGE`, and it has eight entries, which is the number the 200s predict.

**The timeline, from the stream ids and the events themselves:**

| stream id | received | status | service |
|---|---|---|---|
| `1787569930685-0` | 11:12:10.677 | firing | checkoutservice |
| `1787569930685-1` | 11:12:10.677 | firing | frontend |
| `1787569930685-2` | 11:12:10.677 | firing | loadgenerator |
| `1787570140662-0` | 11:15:40.662 | resolved | checkoutservice |
| `1787570155643-0` | 11:15:55.644 | **firing** | **emailservice** |
| `1787570200663-0` | 11:16:40.663 | resolved | loadgenerator |
| `1787570200663-1` | 11:16:40.664 | resolved | frontend |
| `1787570215645-0` | 11:16:55.645 | resolved | emailservice |

The three firing events share a stream-id millisecond, as do the two resolutions at
11:16:40 — separate POSTs arriving inside the same millisecond, which is the same thing the
baseline capture measured as a 1.5ms gap between two deliveries. Ingest publishes them in
arrival order and does not batch them.

## The same delivery shape as the captured baseline

Same rule, same four services, same one-alert-per-POST grouping, and the recovery artifact
in the same place. Two independent injections about forty minutes apart:

| | baseline (`t2.1-webhook`, ~10:32 inject) | live smoke (~11:08 inject) |
|---|---|---|
| deliveries | 8 | 8 |
| alerts | 4, each firing + resolved | 4, each firing + resolved |
| alerts per POST | 1 | 1 |
| services | checkout, frontend, loadgenerator, email | identical |
| post-revert firing | emailservice | emailservice |

**The four fingerprints are byte-identical across the two incidents.**

| service | fingerprint |
|---|---|
| checkoutservice | `13d86469efcf3ccc` |
| frontend | `0eeee852e85422ff` |
| loadgenerator | `7f55ecd578853462` |
| emailservice | `c1cf16569b44acd6` |

This is new information, and it is the strongest confirmation of ADR-0015's identity model
available. The baseline showed a fingerprint stable *within* one episode — firing and
resolved carrying the same value. This shows it stable *across separate incidents*: the
fingerprint is a pure function of the alert's labels and nothing else, so **the fingerprint
alone cannot tell two incidents apart.** That is precisely why the episode key is
`(fingerprint, startsAt)`, and here it does its job — checkoutservice's episode key reads
`13d86469efcf3ccc@2026-08-24T11:12:00.583000+00:00` against the baseline's
`…@10:34:45.583`, same alert, different episode.

**The post-revert `emailservice` firing reproduced.** In the baseline it began at 10:39:30,
about the revert instant, twelve milliseconds before another alert resolved. Here it began
at 11:15:45 and arrived fifteen seconds *after* checkoutservice's resolution, resolving last
of the four again. Second observation of the same phenomenon, on a second injection: the
recovery artifact is a property of this fault, not a one-off. Ingest published it as a new
episode without suppression, which is the behaviour ADR-0015 requires and `tests/test_ingest.py`
pins against the baseline payloads.

Detection lag differed — ~4 minutes from injection to first alert here against ~2m30s in the
baseline. Both are single samples and `CATALOG.md`'s rule applies: a recorded detection time
is what happened once, not a property.

## One event in full

The first entry in `stream-events.txt`, pretty-printed, carrying every field ADR-0015
promises. `generatorURL` is elided at the ellipsis; the file has it whole.

```json
{
  "event_version": 1,
  "received_at": "2026-08-24T11:12:10.676697Z",
  "fingerprint": "13d86469efcf3ccc",
  "episode_key": "13d86469efcf3ccc@2026-08-24T11:12:00.583000+00:00",
  "status": "firing",
  "service": "checkoutservice",
  "starts_at": "2026-08-24T11:12:00.583000Z",
  "ends_at": null,
  "alert": {
    "status": "firing",
    "labels": {
      "alertname": "ServiceHighErrorRate",
      "service_name": "checkoutservice",
      "severity": "critical",
      "signal": "errors"
    },
    "annotations": {
      "description": "checkoutservice is failing 66.67% of calls (baseline 0%).",
      "summary": "checkoutservice error rate above 5%"
    },
    "startsAt": "2026-08-24T11:12:00.583000Z",
    "endsAt": null,
    "generatorURL": "http://0345b24dba28:9090/graph?g0.expr=sum+by%…",
    "fingerprint": "13d86469efcf3ccc"
  },
  "group_key": "{}:{alertname=\"ServiceHighErrorRate\", service_name=\"checkoutservice\"}"
}
```

Three of those fields are worth checking against what the receiver claims to do, because
this is the first time any of it ran outside a test:

- **`ends_at` is `null`, and so is `alert.endsAt`.** Alertmanager sent
  `0001-01-01T00:00:00Z`. The zero-time normalisation fired on the way in and on the way
  out, so no consumer of this stream will ever see the sentinel.
- **`service` is normalised, and `alert.labels.service_name` is untouched.** Every service
  in this incident is already a compose name, so `canonical_service` was a no-op here — the
  field is populated and correct, and this run does not exercise the container-named path.
- **`alert` is the delivery whole**, under Alertmanager's own field names, so nothing about
  the original is only reachable by going back to the webhook.

## Still not exercised

The smoke widens the evidence base but does not close the gaps `t2.1-webhook`'s README
listed, and one of them is the dedupe rule's own subject:

- **Dedupe never fired.** Eight POSTs, eight distinct transitions, zero duplicates. No
  repeat notification (`repeat_interval: 1h`) and no retry occurred, so the suppression path
  has still only ever run against replayed payloads in `tests/test_ingest.py`.
- **No grouped multi-alert payload**, no rule other than `ServiceHighErrorRate`, no
  `ServiceNoTraffic`, and no restart mid-incident — so Redis-backed dedupe surviving a
  process restart is asserted in ADR-0015 and not yet demonstrated.

## Reproducing

Bring up the platform profile for `redis`, run `faultline-ingest`, and inject. Alertmanager
already routes here (`compose/prometheus/alertmanager.yml`). Read the stream with
`redis-cli XRANGE faultline:alerts - +`, and `XLEN faultline:alerts` for a count while it
runs.
