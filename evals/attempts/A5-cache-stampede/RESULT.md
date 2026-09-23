# A5 — cache stampede, as `loadGeneratorFloodHomepage` — RESULT

**Run 2026-09-23 03:30:50 → 03:55:55 UTC, \$0.** One run, `transcript.txt`. The verdicts are the
pre-registered definitions applied to the transcript and nothing else.

## Verdicts

| | verdict | from the transcript |
|---|---|---|
| **PAGES** | **no** | Every poll of `watch.py 12` from 03:30:50 to 03:42:20 was `quiet`; nothing reached `pending`. At minute twelve `frontend` was at **0.00 % errors, p95 23 ms, 149.7 req/s** — against 12.1 req/s before |
| **DISTINCT** | not assessed | The definition applies after it pages |
| **REVERTS** | **yes** | flag off at 03:46:25; nothing to clear; quiet through 03:55:55 |
| **ADMISSIBLE** | **no** | Does not page. The plan's *cache stampede* class, in the only form this world offers it, is not observable through the three rules |

**Prediction scorecard.** PAGES: **right** — *"DOES NOT PAGE … saturation queues rather than
errors, and latency is measured on completed spans"*, confidence high. The reason given was half
right: there was no queueing to hide, because there was no saturation. See below.

## The secondary question, answered as registered

The registration fixed one more question so it could not be invented afterwards: *whether the
world produces any signal a rule could use even if today's three do not*. The answer at minute
twelve:

| service | req/s before → during | p95 before → during | errors |
|---|---|---|---|
| `frontend` | 12.1 → **149.7** (12×) | 48 → **23 ms** | 0 |
| `frontend-proxy` | 5.6 → **74.2** (13×) | 49 → **35 ms** | 0 |
| `load-generator` | 4.9 → **41.5** (9×) | 57 → **43 ms** | 0 |
| everything behind `frontend` | unchanged within noise | unchanged | 0 |

**The only signal is request rate.** The flag makes each locust user, one task in six, issue a
hundred `GET /` in a row (`locustfile.py:218-225`, variant `on` = 100). The frontend served twelve
times its normal traffic with *lower* p95 — the homepage is the cheapest thing it serves, and the
flood shifts the mix toward it. Nothing behind the frontend saw more calls, because the homepage's
server render does not fan out. **There is no saturation here to detect**: at 25 users the flood
is a load spike the world absorbs, not a stampede. A saturation rule on latency or errors would
have been as blind as the three we have, and rightly. The one rule that would fire is a
traffic-rate rule, and that is not a saturation rule; it is an anomaly rule that would fire on a
marketing campaign.

**For Q13 this is the measurement, not the decision**: the flag, as the world ships it, does not
produce a saturation signal at this scale. Whether a larger `LOCUST_USERS` or a larger variant
would — where the frontend's event loop actually falls behind — is a different injection, with
its own registration, and the compose override that would set it is already the mechanism of
`ResourceExhaustionFault`'s neighbour, not a new class.

## A finding for the logs specialist

`shape.py frontend`'s tail was eight lines of **one** error object — the frontend's log of a
failed checkout *from A4b, forty minutes earlier*. The frontend logs errors only, as multi-line
JavaScript objects with a full C# stack trace embedded as a string, and wrote nothing at all
during A5. Two consequences for the catalog: `--tail N` on this service is N lines of one event,
not N events; and a fault on the frontend's *upstream* leaves its trace in the frontend's log
with the upstream's stack inside it — which is the (c) signal for a datastore fault seen from the
caller, and it is richer than the culprit's own line.

## Timeline

| clock (UTC) | event |
|---|---|
| 03:30:50 | flag on |
| 03:30:50–03:42:20 | 24 polls, all quiet |
| 03:42:25 | shape captured: frontend 149.7 req/s, 23 ms, 0 % |
| 03:46:25 | flag off |
| 03:55:55 | recovery window ends, quiet throughout |

**Scoreboard**: eight classes measured (the four existing, `feature_flag`, `process_freeze`,
`network_partition`, `datastore_corruption`); A5 inadmissible; A6, A7, A8 remain. A6 and A7 cannot
add a class by definition; A8 is the last that can, for a ceiling of nine.
