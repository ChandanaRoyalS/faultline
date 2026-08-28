---
origin: scenario:email-wrong-image
split: holdout
fault_class: bad_deploy
recorded_from: 2026-08-28T04:54:58+00:00
capability: cap:9c416e0a
onset_to_page: 4m01s
page_to_fix: 5m00s
fix_to_all_clear: 1m45s
---

# Email service deployed with another service's image

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **checkoutservice**, 4m01s after
onset.

On the storefront, browsing, search and basket operations were normal. Checkout failed.

**emailservice did alert — but late, quietly, and not on anything resembling failure.**
`ServiceNoTraffic` fired on it at **T+6m15s**, two and a quarter minutes after the page
and more than six minutes after onset, and it is the only alert the broken service
produced. It never showed an error rate and never showed latency: a container that
cannot finish starting serves nothing, so the only rule it can eventually trip is the
one that notices an absence. Two alerts across two services, and for the first two and a
quarter minutes the entire signal was one caller failing.

## What was checked

**checkoutservice, named in the page.** Its own process was healthy, its configuration
unchanged, its resources fine. The errors were on one of its outbound calls.

**Which call was failing.** Order confirmation. checkout completes an order and then
hands off to emailservice; that hand-off was returning errors and taking the whole
checkout down with it.

**emailservice's logs, which contain the answer in plain text.** The service was
starting and dying repeatedly — eighteen attempts inside the fault window — and unlike a
process killed from outside, this one printed why every single time:

```
== Sinatra has ended his set (crowd applauds)
[core:warn] [pid 1] AH00111: Config variable ${QUOTE_SERVICE_PORT} is not defined
AH00526: Syntax error on line 5 of /etc/apache2/ports.conf: Port must be specified
```

Three things are wrong with that for a service called email. It is shutting down a Ruby
web framework, then starting Apache, and it is looking for a configuration variable
belonging to an entirely different service.

**What that pattern rules out.** A process that reads its configuration, objects to it,
and exits has got far enough to explain itself. Nothing external stopped it — no memory
ceiling, no scheduler, no dependency. It ran, disagreed with what it found, and quit.
That single distinction eliminates every resource-shaped explanation before any of them
is investigated.

**What changed on emailservice.** Its image reference. A deployment had pointed it at
the quote service's image. The container's environment is exactly what emailservice
needs and has nothing the quote service's code expects, so the process cannot configure
itself and exits on the first read.

## Root cause

A deployment put the wrong image on emailservice. The image resolved and pulled
cleanly, so the deploy reported success; what failed is what the container did next.

**The environment is correct for the service that belongs here and wrong for the image
that was deployed.** Read from the log line alone this looks like a missing
configuration variable, and the instinct is to go and define it. The variable is missing
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

- Onset to first page: **4m01s**.
- Services alerting at the page: **1**. Over the whole incident: **2**, across 2 alerts.
- Alerts that fired only during recovery: **none**.
- **The broken service alerted last, and on absence rather than failure.** Its only alert
  was `ServiceNoTraffic` at T+6m15s — no error rate, no latency, because a container that
  cannot finish starting serves nothing and so fails nothing. A responder working from
  the alert stream alone gets the caller first and the culprit two and a quarter minutes
  later, in a form that says only "this stopped being called" and not "this is broken".
- **Do not wait for the broken service to announce itself.** It did here, eventually, and
  the announcement carried less information than the dependency graph did — following
  checkout's failing outbound call named `emailservice` before the alerting did.
- **Whether a failing process explains itself is the first thing to establish.** A
  process that prints a reason chose to stop; a process whose output ends mid-startup
  with no reason was stopped by something else. Those two have almost disjoint sets of
  causes, and the logs answer it immediately.
- **The logs named the cause outright** and cost nothing to check. The trap is not that
  the evidence is hidden; it is that the alerting points at a healthy service and the
  broken one is invisible, so reaching the logs at all requires following the
  dependency rather than the alert.
- Did the loudest service turn out to be the culprit? **No.** checkoutservice alerted
  for 6.8 minutes against emailservice's 3.2, so the loudest service was the caller and
  the culprit was one hop beyond it — quieter, later, and easy to read as collateral.
