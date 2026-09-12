---
id: world-warm-up-latency
title: A freshly recreated container is not a baseline reading
origin: authored
applies_to: [any]
signals: [ServiceHighLatency]
actions: []
---

Every remediation this system can propose recreates a container. That means the moments right
after a fix look, on the latency metric, a lot like the incident.

## The trap

`ServiceHighLatency` compares p95 against 250 ms with a 3-minute `for` guard. A service that
has just been recreated is still warming - caches cold, connections re-established - and its
p95 sits above baseline for reasons that have nothing to do with any fault. The alert rule's
own description says so.

## Where it bites hardest

Reading a p95 immediately after a proposed fix was applied, and concluding the fix failed.
Or reading one at the start of an investigation on a service something else already restarted,
and concluding a fault exists.

**Check container uptime before trusting a latency number.** It is one query and it separates
a warming service from a degraded one.

## The measured baseline, for comparison

Under 50 ms p95 on every service, flat over 45 clean minutes (ADR-0012). Anything between that
and the 250 ms threshold is neither healthy-by-measurement nor alerting.

**That 45-minute window is not the whole story, and a later twelve-hour census says so**
(ADR-0025). `checkoutservice`, `frontend` and `loadgenerator` spend part of an idle world's time
far above 250 ms in sustained excursions whose cause is accumulated in-process state, not
warm-up; the remaining eleven services sit in a 1.9-9.7 ms band with zero samples over
threshold. That band is a median p95 over the census window, and a service's mean p95 over a
shorter window can sit outside it without contradicting either figure.

Warm-up remains a real transient with a measured shape - a monotonic decay over about four
minutes after a recreate - and container uptime is what separates it from anything else.
