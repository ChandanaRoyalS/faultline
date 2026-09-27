---
origin: scenario:v2-cart-dependency-latency
split: dev
fault_class: dependency_latency
recorded_from: 2026-09-27T08:42:06+00:00
onset_to_page: 4m50s
page_to_fix: 5m00s
fix_to_all_clear: 5m02s
---

# Cart service network path acquires 300ms of delay

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

**On the page:** ServiceHighLatency/cart, ServiceHighLatency/frontend-proxy, ServiceHighLatency/load-generator, ServiceHighLatency/frontend

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+4m50s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighLatency | cart | T-20s | 10.0m |
| **on the page** | ServiceHighLatency | frontend | T-20s | 9.0m |
| **on the page** | ServiceHighLatency | frontend-proxy | T-20s | 9.0m |
| **on the page** | ServiceHighLatency | load-generator | T-20s | 9.0m |
| later | ServiceHighLatency | checkout | T+40s | 8.0m |

The page named 4 service(s). By the time the fault was removed 5 alert(s) had fired - 1 more than the responder saw when they started.

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

- Onset to first firing alert: 4m50s
- Services alerting on the page: 4
- Services alerting by the end of the fault: 5
- Alerts that fired only during recovery: 0
- Steady state held after the page: 5m00s
- Fix to all-clear: 5m02s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
