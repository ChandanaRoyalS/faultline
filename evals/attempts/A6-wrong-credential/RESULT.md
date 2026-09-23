# A6 — wrong database credential on `accounting` ("cert expiry") — RESULT

**Run 2026-09-23 04:25:31 → 04:46:53 UTC for the attempt, then to 05:37:10 for the recovery, \$0.**
The first run at 04:01 was void (`transcript-void-0401.txt`): a bash idiom handed to a zsh user,
compose never ran, nothing was injected. This is the second, `transcript.txt`, and the only one
scored. The verdicts are the pre-registered definitions applied to the transcript and nothing
else — with one verdict the transcript could not return cleanly, and the reason is the attempt's
main finding.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **yes** | `ServiceHighErrorRate/accounting` firing at 04:30:34 — **5 min 03 s** after the recreate, on the target itself. The log names the fault exactly: `SqlState: 28P01 … password authentication failed for user "otelu"`, thrown from `Consumer.ProcessMessage` (`Consumer.cs:90`) |
| **DISTINCT** | not applicable | `BadConfigFault`'s mechanism by definition, as registered |
| **REVERTS** | **the world, yes; the rules, no — until a defect in the telemetry pipeline was found and fixed** | Recreated with the right password at 04:37:20; the error alert drained with the `[5m]` window by 04:42:53 (**5 min 33 s**). The service was consuming and writing orders from the first minute, and Tempo held its traces. Then **`ServiceNoTraffic/accounting` fired at 04:45:53 on a healthy service**, a `docker restart` did not clear it, and its counters stayed frozen for the next 54 minutes. Not the attempt's doing: see below. On the fixed pipeline, `accounting` read **0.589 req/s with nothing firing** at 05:37:10 |
| **ADMISSIBLE** | **no** | Same mechanism as `bad_config`; cannot be a class. **A `bad_config` scenario for T7.1**: it pages on the target, fast, with a log line that names the cause |

**Prediction scorecard.** The registration called PAGES *"a coin flip"* between an eager
connection (crashloop, `ServiceNoTraffic`) and a lazy one where `Consumer.cs` catches, logs and
continues *"in which case the span may not carry an error status and nothing pages"*. It was the
lazy path — the consumer kept consuming and every order failed at the write — **and the spans
carried the error anyway**: the failed connection opens are their own error spans. The registered
worry was wrong in the right direction. Timing 5:03: unregistered, recorded.

## The number that was not a number

`shape.py` at minute twelve read **`accounting 100.00 % errors, 0.137 req/s`**, against 0.505 req/s
before. That is not the service's ratio. The recreate made the container a **new resource** to the
spanmetrics connector, and on this world a new resource of an existing service could only be seen
on label sets the old one had never produced — the error series. Its non-error spans were written
to series the dead container still owned and were refused. **The page was real — every order did
fail at the write, and the error spans alone would clear 5 % of anything — but 100 % is the visible
fraction, not the ratio**, and the 0.137 is the error spans alone. A7, on the fixed pipeline, gives
the first honest ratio for a recreated container.

## What the revert found: the writer that was not single

The full measurement is `docs/evidence/world-v2-trial/2026-09-23-the-writer-that-was-not-single.md`;
the short form:

- **The .NET SDK sets no `service.instance.id`**, so Prometheus names every container that has
  ever run as `accounting` onto one series. The spanmetrics connector keys its counters on every
  resource attribute, never expires a dead resource, and emits it first on every flush. The
  recreated container's samples were refused as duplicates of the dead one's. A restart changed
  nothing because a restart is a recreate.
- **The first fix was wrong.** The demo's own Prometheus `otlp:` block, which our config had
  dropped, was restored (#458) — and after the reload every series still carried
  `host_name="docker-desktop"`, because the demo's `resourcedetection` processor stamps the
  collector host's name over the app's before the connector sees the span. Promotion cannot
  separate what the collector has made identical. The alert *cleared* at 05:17:32 only because the
  series changed label sets under it.
- **The fix is at the connector** (#459): `resource_metrics_key_attributes` keyed on the service
  and its SDK — the README's own remedy for *"changing resource attributes (e.g. process id) …
  breaking counter metrics"*. One service, one counter, one writer; a recreate continues the
  count. Recreating the collector at 05:31:28 put `accounting` back at 0.589 req/s on the first
  flush.

**A1–A5 never recreated a container, which is why this waited for A6.** Every `bad_config` and
`bad_deploy` scenario on v2, and the injector's own restore, would have hit it; **Q89** is the
restore-side consequence — verify the target's rate is *rising*, not that the container runs.

## Timeline

| clock (UTC) | event |
|---|---|
| 04:25:31 | `up -d accounting` with the wrong password; container recreated |
| 04:30:34 | `ServiceHighErrorRate/accounting` (+5:03) — **PAGES** |
| 04:37:10 | shape captured: `100.00 %` / `0.137 req/s` (the visible fraction); `28P01` in the log |
| 04:37:20 | `up -d accounting` with the right password; container recreated — **the world reverts** |
| 04:42:53 | error alert clears (+5:33, the `[5m]` drain) |
| 04:45:53 | `ServiceNoTraffic/accounting` on a healthy service — the defect surfaces |
| 04:50:44 | `docker restart accounting` — no effect (recovery watch to 05:00:15, all firing) |
| 05:04 | exporter log, Tempo and the raw series read: spans present, one flat series, no `instance` |
| 05:15:32 | #458 reloaded — alert clears 05:17:32 by label-set change; number still `0.000` |
| 05:31:28 | #459 — collector recreated with the connector keyed on the service |
| 05:37:10 | `accounting 0.589 req/s`, nothing firing, six quiet minutes — **the rules revert** |

**Scoreboard**: eight classes measured; A6 inadmissible as registered, one `bad_config` scenario
gained; A7 and A8 remain, on a pipeline that now survives a recreate.
