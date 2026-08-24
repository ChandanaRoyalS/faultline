# ADR-0015: Alert identity, dedupe, and the ingest→orchestrator contract

- **Status:** accepted
- **Date:** 2026-08-24
- **Task:** T2.1 (alert ingestion)
- **Evidence:** `docs/evidence/t2.1-webhook/` — eight webhook deliveries captured live
  against a `cart-redis-misconfig` injection

## Context

Ingest is the system's only entry point, and everything downstream inherits whatever it
decides an "alert" is. Gate 1's evidence named fingerprint dedupe as T2.1's job without
saying where a fingerprint comes from or what it identifies, so three questions had to be
settled before any of this could be written: what identifies an alert, what counts as the
same alert seen twice, and how much interpretation ingest is allowed to do.

None of them are answerable from documentation, because the answers depend on what
Alertmanager actually sends under *our* routing config. So they were measured first. The
capture is eight deliveries — four alerts, each delivered once firing and once resolved —
and the evidence README carries the full field inventory. Three findings drive everything
below:

- **Alertmanager supplies a `fingerprint`, and it is stable.** The resolved delivery
  repeats the firing delivery's fingerprint exactly, it differs per label set, and it is
  unmoved by annotation drift — `frontend`'s rendered description said `29.25%` firing and
  `10.08%` resolved under one fingerprint.
- **Every delivery carried exactly one alert, because of our `group_by`.** The grouping key
  `[alertname, service_name]` is as fine as the alerts themselves. This is a property of a
  file we edit, not of the protocol.
- **A recovery artifact arrives as a fresh alert.** `emailservice` began firing at
  `10:39:30`, about the instant of the revert, twelve milliseconds before another alert of
  the same incident resolved, and resolved last of the four. Nothing in the payload marks
  it as recovery.

## Decision

### Identity: the fingerprint is the alert, `(fingerprint, startsAt)` is the episode

**We compute no fingerprint of our own.** Alertmanager's is stable across the lifecycle,
distinct per label set, and independent of the annotation values that change between
deliveries — measured, above. A fingerprint we derived ourselves would at best reproduce
it and at worst disagree with it.

`fingerprint` names the alert across all of its firings. `startsAt` separates one firing
from the next, so `(fingerprint, startsAt)` names one **episode**: one firing-to-resolved
lifetime. Both are carried on the event as `fingerprint` and `episode_key`.

### The dedupe rule

**The same `(fingerprint, startsAt, status)` seen again is a repeat notification, and
produces no second event.**

Adding `status` to the key is what keeps an episode's close distinct from its open. Keying
on `fingerprint` alone would collapse firing and resolved into one transition and the
incident would never be seen to end; keying on `(fingerprint, startsAt)` without `status`
does the same thing.

What this suppresses is `repeat_interval` re-notifications (1h in our config) and
Alertmanager retries of a delivery we failed to accept. Neither is new information, and
both would otherwise open a second incident for one alert.

Note what the capture could *not* show: it spans six minutes, so no repeat notification and
no retry occurred in it. The rule is written against a case the evidence does not contain,
which is stated here rather than left to look measured. What the evidence does establish is
the identity the rule keys on.

### Dedupe state lives in Redis, not in the process

**Because it has to survive a restart.** A receiver restarted between an alert's first
notification and its hourly repeat has no memory of the first, so an in-process dict makes
every restart a source of duplicate incidents — and a deploy is both a restart and a
likely-alerting moment. Redis is already in the stack (ADR-0001), so this adds no
operational surface: `SET key NX EX ttl`, one round trip, atomic by construction, with a
seven-day TTL bounding the key space without a sweeper.

The TTL is the one number here with a failure mode: an expiry while an alert is still
firing makes the next repeat look new. Seven days against a 1h `repeat_interval` is a wide
margin, and an alert firing for a week is a different problem.

`EpisodeLog` is a Protocol with a Redis implementation and an in-memory one. The in-memory
one is for tests and is documented as such — it is the same rule with the only property
that matters in production removed.

### Ingest does not decide what an incident is

**Its contract is faithful, deduplicated delivery of alert-episode transitions.** That is
the whole of it.

A `resolved` delivery for an episode closes that episode by publishing its close. A firing
for a *new* episode arriving during another's resolution is published, in arrival order,
with no suppression and no annotation — which is exactly the `emailservice` case. Ingest
does not ask whether that alert belongs to the incident that is closing.

That question is correlation, it is **T2.2's**, and putting it here would be wrong on the
merits rather than merely misplaced: correlation needs the dependency graph, the incident
state machine, and a policy about what "same incident" means, none of which ingest holds.
An ingest that guessed would either merge a genuine second incident into a closing one or
split one incident in two, and would do it silently, before anything durable had been
written.

A `resolved` for an episode ingest never saw open — after a restart, or a receiver that was
down for the firing — is also published. Dropping it would be ingest deciding the episode
does not matter, which is the same call under a different name.

### The event shape, as the contract T2.2 consumes

One `XADD` per event onto `faultline:alerts`, the whole event as JSON under a single
`event` field. Streams take flat field-value maps and this event is not flat — the alert as
delivered is nested — so splitting it across fields would invent a second encoding of
something ingest already had in one piece.

| Field | Content |
|---|---|
| `event_version` | `1`. Bump only for a breaking change. |
| `received_at` | The receiver's clock at delivery. |
| `fingerprint` | Alertmanager's, unmodified. The alert. |
| `episode_key` | `<fingerprint>@<startsAt>`. The episode. |
| `status` | `firing` or `resolved`. |
| `service` | `service_name` through `canonical_service`, or `null`. |
| `starts_at` / `ends_at` | `ends_at` is absent while firing (below). |
| `alert` | The full alert object as delivered, under Alertmanager's field names. |
| `group_key` | The Alertmanager group that carried it. |

Two of those need their reasoning recorded.

**`service` is normalised, and the raw label is kept.** The world names every service twice
— compose `cartservice`, container `cart-service` — and which name appears depends on what
produced it. `canonical_service` collapses that so the orchestrator can key on one identity
without knowing the schemes exist; `alert.labels.service_name` still holds exactly what
arrived. It is `null` when the alert has no `service_name`, because not every rule is
per-service and inventing one would be worse than admitting it.

*Layering note:* `canonical_service` lives in `injector.world`, so the product runtime now
imports from the injector. That map describes the demo world specifically. It is the right
source today and the wrong shape for a deployment that is not this demo — revisit when a
second target environment appears, not before.

**`endsAt` is absent while firing, not a date.** Alertmanager sends Go's zero `time.Time`,
`0001-01-01T00:00:00Z`, which parses as a valid timestamp and is not one. Left alone it
reads as an alert that ended two thousand years ago, and any "is this over?" comparison
answers wrongly and with confidence. It is normalised to `null` on the way out, so no
consumer has to know the sentinel exists.

**`alerts` is iterated, never indexed.** One alert per POST is our `group_by` and not the
protocol's. Editing `compose/prometheus/alertmanager.yml` would put several alerts behind
one request with no other signal, and code written against `alerts[0]` would start dropping
alerts silently. The unit is the alert; the POST is transport.

**Inbound models allow unknown fields.** Everything internal in this repo forbids extra
fields; these two do not, deliberately. This is external input from a component we do not
version-pin to ourselves, and a future Alertmanager adding a field must not turn every
delivery into a 422 and drop real incidents. Unknown fields are carried through to the
stream rather than discarded, so nothing is lost by tolerating them.

## Consequences

**Easier.** T2.2 receives a clean, ordered, deduplicated stream of transitions with stable
identity on each one, and is free to define correlation without unpicking a guess ingest
already made. The receiver is a pure function over a payload plus two Protocols, so its
whole test suite runs against the real captured deliveries with no Redis and no network.

**Harder.** Correlation is now unambiguously T2.2's problem and it is the harder half —
ingest handing over transitions rather than incidents means T2.2 owns every judgement about
what belongs together. The `emailservice` case is the concrete one waiting there.

**Untested, and named as such.** Retries against a down receiver, repeat notifications,
grouped multi-alert payloads, and any rule other than `ServiceHighErrorRate` are all
outside the capture. The receiver handles the grouped case by construction and it is tested
against a payload assembled from real alerts, but no Alertmanager has ever sent us one.

**The port has no authentication.** Measured: no signature, no shared secret, no credential
of any kind on any delivery. Anything that can reach it can fabricate an incident.
Validation is the only thing at that boundary today. Recorded in `docs/THREAT-MODEL.md`;
the defence is T2.6/T6.8's and is deliberately not built here.

**Known bug, ~~not fixed here~~ closed at T2.2: `faultline-ingest` ignored `--help` and
started the server.** Found during the live smoke. `run()` took no arguments and handed
control straight to uvicorn, so every flag - including the one every reader tries first - was
swallowed and the process bound a port instead of describing itself. It was recorded rather
than patched because the entry point would want real arguments eventually (`--host`,
`--port`, at least `--stream`) and bolting on a `--help` special case would have been the
wrong shape; the stated condition was "whoever adds those adds argument parsing, and this
stops being true".

T2.2 added `faultline-orchestrate`, a second CLI with the same need, which is when that
condition was met. Both now parse arguments, and both `--help` without reaching Redis or
Postgres - the backends are imported inside `run()`, after parsing.

**Revisit if:** Alertmanager's fingerprint stops being stable across a lifecycle (dedupe
would silently split every alert in two, so this is worth a guard when the ingest path
grows one), a second producer appears that has no fingerprint of its own, or a deployment
target arrives whose service naming `injector.world` does not describe.
