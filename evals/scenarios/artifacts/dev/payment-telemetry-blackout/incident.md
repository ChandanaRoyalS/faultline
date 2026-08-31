---
origin: scenario:payment-telemetry-blackout
split: dev
fault_class: bad_config
recorded_from: 2026-08-31T02:34:36+00:00
capability: cap:9c416e0a
onset_to_page: 6m16s
page_to_fix: 5m00s
fix_to_all_clear: 1m02s
---

# Payment service healthy, serving, and invisible in the traffic metric

<!-- NO ABSOLUTE TIMESTAMPS IN THE PROSE. Write "T+3m" or "about four minutes after
     the page", never "08:02:41". This file is read months later as a past incident,
     where the hour it happened means nothing - and a re-record would orphan every
     timestamp written here.

     `recorded_from` in the front matter above is the deliberate exception. It is
     absolute precisely so that it breaks when the recording changes: it pins this
     narrative to one recording, and a guard fails if they drift apart. Front matter
     is written to fail on a re-record; prose is written to survive one. Do not
     "fix" the inconsistency - see ARTIFACTS.md. -->

## What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

**On the page:** ServiceNoTraffic/paymentservice

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+6m16s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceNoTraffic | paymentservice | T-16s | 6.0m |

## What was checked

**Whether anything downstream of payment was failing.** Nothing was. Checkout's error ratio was
flat at zero for the whole window, and no error-rate or latency alert fired on any service. For a
service that had supposedly stopped serving, this was the wrong shape entirely - when payment is
genuinely unavailable, checkout is the first thing to break, and it had not.

**Whether checkout was still calling payment at all.** It was. Checkout's client spans to
paymentservice continued throughout and continued to return normally. That ruled out the
possibility that traffic had simply stopped arriving - somebody was still calling, and the calls
were being answered.

**Payment's own logs.** This is what settled it. The container logged `Charge request received.`
continuously through the entire window - 111 of them across the minutes the alert was firing,
carrying trace ids and card details as usual. A process that is down does not log; this one was
handling charges the whole time it was reported as serving none.

**Dead end: looking for a crash or a restart.** Container status, restart count and memory were all
checked first, because `ServiceNoTraffic` normally means something died. Nothing had. The container
had been up since the start of the window and showed no restarts and no memory pressure.

**Dead end: looking for the cascade.** Every previous `ServiceNoTraffic` on this system arrived with
company - a fan of alerts across the services that depend on the dead one. This one was alone, and
that was treated as suspicious rather than lucky.

**What named it:** the change history on paymentservice, which showed its OTLP trace exporter
endpoint had been changed to an address that does not answer.

## Root cause

The payment service's trace exporter was pointed at an address with nothing listening on it, so the
service stopped shipping spans. Nothing about the service itself changed: it kept accepting charges
and kept logging them. The traffic metric that `ServiceNoTraffic` watches is built from those spans,
so when the spans stopped the metric went to zero and the alert fired on a service that was working
normally the entire time. The outage was in the reporting path, not in the payment path.

## Resolution

The exporter endpoint was set back to the collector, and the traffic metric recovered within about a
minute of the service picking the setting up. **Class of fix: `config_revert`** - a setting was
returned to its previous value. Nothing was rolled back, restarted for its own sake, or resized; the
service had never been unhealthy.

## Detection notes

- Onset to first firing alert: 6m16s
- Services alerting on the page: 1
- Services alerting by the end of the fault: 1
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 1m02s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
