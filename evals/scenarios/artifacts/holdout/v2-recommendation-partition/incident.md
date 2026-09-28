---
origin: scenario:v2-recommendation-partition
split: holdout
fault_class: network_partition
recorded_from: 2026-09-28T11:46:36+00:00
onset_to_page: 6m46s
page_to_fix: 5m00s
fix_to_all_clear: 6m01s
---

# The recommendation service is cut from the network - its process runs and reaches nothing

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

**On the page:** ServiceHighLatency/load-generator, ServiceHighLatency/frontend-proxy

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+6m46s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighLatency | frontend-proxy | T-16s | 9.0m |
| **on the page** | ServiceHighLatency | load-generator | T-16s | 9.0m |
| later | ServiceNoTraffic | recommendation | T+44s | 5.0m |

The page named 2 service(s). By the time the fault was removed 3 alert(s) had fired - 1 more than the responder saw when they started.

#### Fired only after the fix was applied

<!-- These are the recovery, not the incident: the fault was already gone when
     they started. Recreating a container has its own failure modes. Mention
     them if they mattered to the responder, but do not count them as the
     fault's blast radius. -->

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| later | ServiceHighErrorRate | frontend | T+7m44s | 2.0m |
| later | ServiceHighErrorRate | recommendation | T+7m44s | 2.0m |
| later | ServiceHighLatency | frontend | T+8m44s | 1.0m |
| later | ServiceHighLatency | recommendation | T+8m44s | 2.0m |

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

- Onset to first firing alert: 6m46s
- Services alerting on the page: 2
- Services alerting by the end of the fault: 3
- Alerts that fired only during recovery: 4
- Steady state held after the page: 5m00s
- Fix to all-clear: 6m01s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
