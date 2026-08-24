---
origin: scenario:email-wrong-image
split: holdout
fault_class: bad_deploy
recorded_from: 2026-08-24T02:55:23+00:00
onset_to_page: 4m16s
page_to_fix: 5m00s
fix_to_all_clear: 1m00s
---

# Email service deployed with another service's image

## What was observed

One alert: `ServiceHighErrorRate` on **checkoutservice**, 4m16s after onset. Nothing
else fired for the whole incident.

On the storefront, browsing, search and basket operations were normal. Checkout failed.

**emailservice never appeared in the alerting at any point** — not on error rate, not
on latency, not on traffic. The only evidence in the alert stream was one of its
callers failing.

## What was checked

**checkoutservice, named in the page.** Its own process was healthy, its configuration
unchanged, its resources fine. The errors were on one of its outbound calls.

**Which call was failing.** Order confirmation. checkout completes an order and then
hands off to emailservice; that hand-off was returning errors and taking the whole
checkout down with it.

**emailservice.** The container existed and was in a restart loop, **exiting 1** — not
killed by the kernel, not out of memory. The process was choosing to stop, which means
it had something to say about why.

**The logs, which contain the answer in plain text.**

```
AH00526: Syntax error on line 5 of /etc/apache2/ports.conf: Port must be specified
AH00111: Config variable ${QUOTE_SERVICE_PORT} is not defined
```

Two things are wrong with that for a service called email. It is running Apache, and it
is looking for a configuration variable belonging to an entirely different service.

**What changed on emailservice.** Its image reference. A deployment had pointed it at
the quote service's image. The container's environment is exactly what emailservice
needs and has nothing the quote service's code expects, so the process cannot configure
itself and exits on the first read.

## Root cause

A deployment put the wrong image on emailservice. The image resolved and pulled
cleanly, so the deploy reported success; what failed is what the container did next.

**The environment is correct for the service that belongs here and wrong for the image
that was deployed.** Read from the log line alone this looks like a missing
configuration variable, and the instinct is to go and add it. The variable is missing
because the wrong thing is asking for it, and defining it would make a service that
should not be running run slightly further.

## Resolution

The image reference was restored. emailservice came up on the next reconciliation and
checkout succeeded immediately. Everything was clear **60 seconds** after the fix —
nothing had to drain or reconnect, and the checkout path recovered as soon as its
dependency answered.

Class of fix: **rollback**. A deployment moved the service to the wrong artifact; the
fix was to put the previous one back.

## Detection notes

- Onset to first page: **4m16s**.
- Services alerting at the page: **1**. Over the whole incident: **1**, across 1 alert.
- Alerts that fired only during recovery: **none**.
- **The broken service never alerted.** No error rate, no latency, no absence of
  traffic. A container that cannot finish starting records nothing at all, and this one
  did not stay dead long enough in any single window to register as silent either. The
  entire signal was one caller failing.
- **The exit code narrows the search before the logs do.** Exit 1 is a process deciding
  to stop; a process killed for resources exits 137. That difference is the whole
  distinction between reading the logs and not bothering — a resource kill leaves
  nothing to read, and this did not.
- **The logs named the cause outright** and cost nothing to check. The trap is not that
  the evidence is hidden; it is that the alerting points at a healthy service and the
  broken one is invisible, so reaching the logs at all requires following the
  dependency rather than the alert.
- Did the loudest service turn out to be the culprit? **No** — but it was the only
  service that alerted, so "loudest" and "only" were the same thing, and the culprit was
  one hop beyond it.
