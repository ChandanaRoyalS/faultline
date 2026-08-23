---
origin: scenario:product-catalog-flag-failure
split: dev
fault_class: bad_config
recorded_from: 2026-08-23T17:48:08+00:00
onset_to_page: 3m24s
page_to_fix: 7m09s
fix_to_all_clear: 48s
---

# A feature flag turned on at the flag service makes product catalog fail one product

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

**On the page:** ServiceHighErrorRate/loadgenerator

### How the alert set evolved

<!-- Describe the spread in prose too, not just the table: which service went first, what
     followed it, and how long the gap was. A reader looking this up months later needs
     the shape of the cascade, not only its final size. -->

The page went out **T+3m24s** after onset. Times below are relative
to the page.

| When | Alert | Service | Started | Firing for |
|---|---|---|---|---|
| **on the page** | ServiceHighErrorRate | loadgenerator | T+6s | 7.8m |
| later | ServiceHighErrorRate | frontend | T+21s | 7.5m |
| later | ServiceHighErrorRate | productcatalogservice | T+21s | 7.5m |

The page named 1 service(s). By the time the fault was removed 3 alert(s) had fired - 2 more than the responder saw when they started.

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

- Onset to first firing alert: 3m24s
- Services alerting on the page: 1
- Services alerting by the end of the fault: 3
- Alerts that fired only during recovery: 0
- Steady state held after the page: 7m09s
- Fix to all-clear: 48s
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
- Would the page alone have led you to the right service? <!-- yes / no -->
