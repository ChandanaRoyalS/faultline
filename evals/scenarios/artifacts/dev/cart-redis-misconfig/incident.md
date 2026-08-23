---
origin: scenario:cart-redis-misconfig
split: dev
fault_class: bad_config
injected_at: 2026-08-23T05:09:00+00:00
resolved_at: 2026-08-23T05:16:31+00:00
---

# Cart service pointed at the wrong Redis port

## What was observed

<!-- Write this as the on-call engineer would have experienced it, NOT as someone who
     knew the answer. No mention of the injector. This text is retrieved later as a past
     incident, so an answer written from hindsight teaches the agent to cheat. -->

Alerts that fired: ServiceHighErrorRate/checkoutservice, ServiceHighErrorRate/frontend, ServiceHighErrorRate/loadgenerator

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

- Time from fault to first firing alert: 180s
- Services that alerted: 3
- Did the loudest service turn out to be the culprit? <!-- yes / no - this one matters -->
