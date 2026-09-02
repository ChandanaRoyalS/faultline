---
origin: scenario:shipping-wrong-image
split: dev
fault_class: bad_deploy
recorded_from: 2026-08-30T01:36:51+00:00
capability: cap:c4d52d00
onset_to_page: 3m18s
page_to_fix: 5m00s
fix_to_all_clear: 2m01s
---

# Shipping service deployed with another service's image

## What was observed

The page was a single alert: `ServiceHighErrorRate` on **checkoutservice**, 3m18s after
onset. The fastest page this system has produced, and unusually it named a service one
hop from the problem rather than the edge.

For three and a half minutes it was the only alert. Then five services raised
`ServiceNoTraffic` — quoteservice at **T+6m00s**, then accountingservice, emailservice,
frauddetectionservice and **shippingservice** fifteen seconds behind it.

**frontend** and **loadgenerator** crossed the error threshold last of all, at
**T+6m30s**, and stayed up for two minutes. The storefront was failing on checkout only,
so its diluted error ratio took nearly four minutes longer to cross than checkout's did.

Eight alerts across eight services. On the storefront, browsing and basket operations
worked normally. Checkout failed every time.

## What was checked

**checkoutservice, named in the page.** Errors on its calls to shipping. Its own
process was healthy, its configuration unchanged, its other dependencies fine.

**shippingservice's logs.** The service was starting and dying, over and over. Fifteen
attempts inside the fault window, each one exactly three lines long — a JVM banner, a
class-loading warning, an instrumentation agent announcing its version — and then
nothing. The gaps between attempts lengthen from five seconds to a minute and stay
there, which is a supervisor backing off a container that will not stay up.

**And this is where a confident wrong answer is available.** A JVM that dies partway
through startup, repeatedly, on a lengthening backoff, saying nothing about why, is
exactly what a memory limit set below what the service needs looks like. The signature is
identical. The diagnosis writes itself and the obvious fix is to raise the ceiling.

**What the process never said.** Not one line explains a failure. That absence is
itself informative: a process that fails on its own configuration prints the reason,
because it got far enough to read the configuration and object to it. This one is being
stopped from outside before it reaches that point — killed, not failing.

**The logs from before onset, which is where it breaks open.** Up to 18:29:28 the
container is emitting Rust — structured request lines from the shipping implementation,
`ShipOrderRequest`, quote calculations, tracking IDs. From 18:29:33 it emits JVM startup
banners and nothing else. **The service changed language across the boundary.** No
resource limit does that. Whatever is running in that container is not the program that
was running five seconds earlier.

**What changed on shippingservice.** Its image reference. A deployment had pointed it at
a different service's image — one built on a JVM, where the previous image was a small
native binary. The new image needs several times the memory the old one did, and the
container ceiling was sized for the old one.

**The memory limit, which had not changed.** Its ceiling was the same value it had been
for weeks. Nothing had lowered it. A service does not begin exceeding a limit it has
lived comfortably inside unless something about the service changed.

## Root cause

A deployment put the wrong image on shippingservice. The image resolved and pulled
cleanly, so the deploy itself reported success; the failure is entirely in what the
container did afterwards. It could not start inside a memory ceiling sized for the
service that was supposed to be there.

The observable symptom belongs to resource exhaustion. The cause is a deployment, and
the two are separated by what changed: the image moved, the limit did not.

## Resolution

The image reference was restored. shippingservice came up on the next reconciliation and
checkout succeeded immediately. The no-traffic alerts cleared as those services resumed.
A brief `ServiceHighErrorRate` appeared on frontend fifteen seconds *after* the fix and
lasted half a minute — queued work draining through a path that had been failing.
Everything was clear at **T+7m01s**.

Class of fix: **rollback**. A deployment moved the service to the wrong artifact, and
the fix was to put the previous one back.

**Raising the memory limit would also have stopped the alert, and would have been
worse.** The container would have started, stayed up, and answered on the wrong
protocol — a service reporting healthy while every caller fails, which is harder to
diagnose than a container that cannot start.

## Detection notes

- Onset to first page: **3m18s**, the fastest on this system. A dependency whose failure
  is fatal to its caller pages quickly; one whose failure is tolerated does not.
- Services alerting at the page: **1**. Over the whole incident: **8**, across 8 alerts.
- Alerts that fired only during recovery: **none**.
- **The page named the caller, not the edge and not the culprit.** checkoutservice fails
  outright when shipping is unavailable, so its error ratio crosses the threshold before
  the frontend's diluted one does. Being one hop from the fault made it the earliest and
  most specific signal available.
- **Dilution is measurable here, and it is worth nearly four minutes.** checkout, which
  fails on every attempt, alerted at T+2m45s; frontend and the synthetic client, whose
  failures are one path out of many, did not cross until T+6m30s. The same failure
  reaches the edge last and weakest, so a responder who waits for the storefront to look
  broken is choosing to start four minutes late.
- **A truncated, repeating startup names a symptom, not a cause.** A process stopped
  before it can explain itself is being killed from outside, and that is all the pattern
  says. It does not distinguish "the ceiling came down" from "the thing inside it got
  bigger", and those have opposite fixes.
- **What separated them was the log content before onset**, not the failure itself. The
  container was running one language and then another. A service whose runtime changes
  has been redeployed, whatever else is true — and no resource limit produces that.
  Where a substituted image happens to share a runtime with the original, this signal
  would not exist and the change history would be the only route.
- The strongest single question remained **"what changed on this service?"** Any
  investigation that stopped at the restart pattern would have shipped a fix that made
  the system quieter and worse.
