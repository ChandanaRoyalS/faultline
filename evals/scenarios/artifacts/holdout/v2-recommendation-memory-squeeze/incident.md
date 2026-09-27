---
origin: scenario:v2-recommendation-memory-squeeze
split: holdout
fault_class: resource_exhaustion
recorded_from: 2026-09-27T20:55:24+00:00
capability: cap:d2b243e0
onset_to_page: 5m16s
page_to_fix: 5m00s
fix_to_all_clear: 3m00s
---

# Recommendation service memory limit cut below what its interpreter needs to start

## What was observed

The page was `ServiceHighErrorRate` on the **frontend** and **frontend-proxy** together, 5m16s
after the trouble started. Three minutes later `ServiceNoTraffic` fired on **recommendation**.
Three alerts on three services; nothing else fired, then or later, and nothing fired after the fix.

The frontend's error ratio had been zero. It was 2% a minute in, 4.9% at two, 6.2% at three, 8.1%
at four, and from then it sat between 5.9 and 9.9% for as long as the trouble lasted, the proxy's
a fraction under it all the way. The load generator's followed at about half - 3 to 5% - and
touched the line for a minute without holding it. Not one latency moved: the frontend's p95 sat at
its usual 42 to 45ms, the proxy's and the load generator's likewise. Checkout placed orders at its
usual rate with no errors at all - 91 completed - and payment, shipping, email and the rest kept
their rates. The catalog's rate fell from about 5 lookups a second to about 3, with no errors and
its p95 easing from 6ms to 3.

What went missing was recommendation. Its span rate had been 0.5 to 0.7 a second. It was 0.43 a
minute in, 0.28 at two, 0.14 at three, 0.01 at four, and nothing from five; from then on its error
ratio and its latency had no value at all. It had recorded no error of its own before its numbers
ran out, and no rise in latency.

## What was checked

**The frontend's error traces, the service on the page.** 129 of them across the ten minutes, and
every one is the same request: a `user_get_recommendations` page load ending at
`grpc.oteldemo.RecommendationService/ListRecommendations` with **nothing beneath it** - no
recommendation span, no catalog lookups after it, because the four product lookups a
recommendation strip needs never got their list. Beneath the call, the frontend's own attempts:
`dns.lookup`, then `tcp.connect` refused at recommendation's address, five times in a row, then
`connect EHOSTUNREACH` at the same address, some of those attempts waiting three seconds, one
fourteen, one thirty-eight, and once `getaddrinfo ENOTFOUND recommendation`. The request itself
failed in about 20ms; the long waits are the client's connection attempts continuing in the
background, and they say what the address was doing: refusing, then unreachable, then not
resolving at all - a container that is there and not listening, then gone, then back and gone
again. Every recommendation request in the incident failed. Every other request kind succeeded:
checkout has no error trace, and the catalog's error ratio stayed at zero.

**Whether recommendation was idle or gone.** Gone. Its 20 runtime series - interpreter memory,
CPU, threads, garbage collection - held their last values for the store's lookback and then had
no value from about T+5 until after the fix. A process that is merely idle keeps exporting them.
Nothing called on it was answered, nothing it owns was reported, and the frontend's connection
attempts found nothing listening at its address for ten minutes.

**Recommendation's log, which says nothing at all.** Its last line came 0.6 seconds before the
trouble began - an ordinary `Receive ListRecommendations` - and then **nothing**: no error, no
traceback, no shutdown line, not even a start-up banner, for eleven minutes. The next line is the
one a fresh process writes when it is up - `Recommendation service started, listening on port
9001` - 48 seconds after the fix, followed by ordinary requests. A process that is killed writes
nothing, and a process that is killed before it finishes starting never gets as far as its first
line; a log that simply stops and resumes with a start-up line is the signature of a process that
was killed, and killed again, and only once allowed to start.

**What changed.** No deploy, no image change - the same `2.2.0-recommendation` before and after -
no environment change, no flag. One record, at onset, under recommendation's name: `memory limit
lowered on recommendation`, to `memory=16m`, from 500M. Recommendation had been using 46MB at rest,
and an interpreter of its kind needs more than 16MB simply to finish loading. The record names a
ceiling below what the process needs to exist, and the log names the second it stopped.

**What it was not.** A wrong image - that shows another program's output in the log and an image
in the record, and here the log is empty and the record is a limit. A slow catalog behind it -
that shows latency on recommendation with recommendation present, and here nothing is slow and
recommendation is absent. A flag - that leaves no record and a process that stays up and keeps
exporting. A starved process that still fits - that shows a slow service, restarts announcing
themselves in the log, and latency on the target; here there is no latency anywhere and the log
has no start-up line until the fix, because no process ever got that far.

## Root cause

The recommendation service container's memory limit was lowered from 500M to 16m, below what its
Python interpreter needs to finish starting. The kernel killed the running process at once and
killed every replacement before it could listen, so the service was never available for the whole
incident: the storefront's recommendation requests all failed, the frontend and its proxy paged on
the errors, and recommendation itself went silent - no spans, no series, no log, because nothing
survived long enough to write. Nothing about its image, code or configuration changed; restoring
the limit fixed it.

## Resolution

The memory limit was restored to 500M. The restart policy had backed off to about a minute between
attempts by then, so the next start came 47 seconds after the fix, and that one finished: the
start-up line at 48 seconds, the first recommendation served nine seconds after that, and its
rate climbing back through its window from then on. `ServiceNoTraffic` cleared 1m44s after the
fix and the two error-rate alerts 2m44s after it, as their windows drained; the world was all
clear 3m00s after the fix, and nothing fired during recovery.

Class of fix: **config_revert**. The container's resource limit was wrong and it was set back.
Restarting recommendation was what the runtime had been doing, nineteen times, and none of those
starts could finish under the limit; rolling back its image would have changed nothing, because
the image was never the problem.

## Detection notes

- Onset to first page: **5m16s**, the frontend's five-minute error ratio crossing 5% and holding
  for the rule's two minutes. Services on the page: **2**, frontend and frontend-proxy, neither the
  culprit. By the fix: **3**, the culprit last.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** The frontend and its proxy paged
  first and longest, and the frontend's own error traces name recommendation in their first line.
- Would the page alone have led you to the right service? **Not on its own.** The page names the
  callers; the callers' traces name the leaf; the leaf's silence names the class.
- **A leaf that fails fast pages its callers on errors, not latency.** Every recommendation
  request failed in about 20ms, so the frontend's error ratio climbed and its p95 never moved. The
  same absence on a caller that waits would have paged on latency instead.
- **The page arrives when the arithmetic says.** A recommendation request errors four frontend
  spans and two proxy spans; at the frontend's request mix that is 6 to 10% of its spans, over a
  5% line, and the load generator's one span per request stayed under it. The page is a function
  of the callers' span counts, not of how broken the leaf is.
- **An empty log is not a healthy service.** No error, no traceback, no banner: the process never
  got far enough to write one. Read the stop off the last ordinary line and the death off the
  series; the cause is in the change record.
- **The frontend's connection attempts tell the container's story.** Refused, unreachable, not
  resolving: there and not listening, gone, and back and gone again - a restart loop seen from
  the outside, without the container being visible at all.
- **Recovery waits on the restart policy's backoff.** The limit was restored at once; the next
  start took 47 seconds to come, because the runtime had backed off to a minute after nineteen
  kills. A fix to a crash-looping service takes effect on the next attempt, not immediately.
