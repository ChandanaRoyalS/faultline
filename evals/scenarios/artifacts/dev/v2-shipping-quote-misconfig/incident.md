---
origin: scenario:v2-shipping-quote-misconfig
split: dev
fault_class: bad_config
recorded_from: 2026-09-25T00:48:23+00:00
onset_to_page: 4m19s
page_to_fix: 5m00s
fix_to_all_clear: 5m02s
---

# Shipping service pointed at a quote service that does not resolve

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

**On the page:** ServiceHighErrorRate/checkout, ServiceHighErrorRate/shipping

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+4m19s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighErrorRate | checkout | T-4s | 9.0m |
| **on the page** | ServiceHighErrorRate | shipping | T-4s | 10.0m |
| later | ServiceHighErrorRate | frontend | T+1m56s | 4.0m |
| later | ServiceHighErrorRate | frontend-proxy | T+1m56s | 5.0m |
| later | ServiceNoTraffic | accounting | T+3m56s | 2.0m |
| later | ServiceNoTraffic | email | T+3m56s | 2.0m |
| later | ServiceNoTraffic | payment | T+3m56s | 2.0m |
| later | ServiceNoTraffic | quote | T+3m56s | 2.0m |
| later | ServiceHighErrorRate | fraud-detection | T+4m56s | 2.0m |

The page named 2 service(s). By the time the fault was removed 9 alert(s) had fired - 7 more than the responder saw when they started.

#### Fired only after the fix was applied

<!-- These are the recovery, not the incident: the fault was already gone when
     they started. Recreating a container has its own failure modes. Mention
     them if they mattered to the responder, but do not count them as the
     fault's blast radius. -->

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| later | ServiceHighLatency | fraud-detection | T+5m56s | 1.0m |

## What was checked

<!-- The signals a responder would reach for, in order, including the ones that turned
     out to be dead ends. Dead ends are valuable - they are what distinguishes a real
     investigation from a lookup. -->

## Root cause

<!-- One paragraph, plain language. -->

## Resolution

<!-- What fixed it, and what class of fix that is: rollback / restart / config_revert /
     scale. Must match the scenario's expected_remediation_class. -->

## Detection notes

- Onset to first firing alert: 4m19s
- Services alerting on the page: 2
- Services alerting by the end of the fault: 9
- Alerts that fired only during recovery: 1
- Steady state held after the page: 5m00s
- Fix to all-clear: 5m02s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
