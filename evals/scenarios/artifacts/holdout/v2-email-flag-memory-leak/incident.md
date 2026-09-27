---
origin: scenario:v2-email-flag-memory-leak
split: holdout
fault_class: feature_flag
recorded_from: 2026-09-27T06:11:33+00:00
capability: cap:d2b243e0
onset_to_page: 4m16s
page_to_fix: 5m00s
fix_to_all_clear: 5m01s
---

# A feature flag makes the email service keep every confirmation it sends

## What was observed

The page was one alert, `ServiceHighLatency` on **email**, 4m16s after the trouble started. A
minute and three quarters later `ServiceHighLatency` fired on **checkout** too. Nothing else fired,
then or later, and nothing fired after the fix.

Email's p95 had been 37 to 43ms. A minute in it was 770ms, and it held between about 770 and 850ms
for as long as the trouble lasted. Email raised no errors at all. Its span rate fell from about 0.5
a second to between 0.2 and 0.38, so a good part of its usual work was not being recorded.

Checkout's p95 followed it up, from about 35ms to 225ms at two minutes and 560 to 585ms from four
minutes on. Its error ratio rose too, to between 1.7% and 3.6%, under the line. Around them almost
nothing moved. Payment, accounting and fraud-detection kept their usual rates, so orders were
being placed, charged and recorded. The storefront slowed a little, frontend-proxy's p95 from about
45 to at most 132ms. A few services that read flags, and flagd itself, showed a sliver of errors,
0.4 to 2.3%, from seven to ten minutes in, the same sliver they had shown in the three minutes
before the trouble started. Nothing else's error ratio moved.

## What was checked

**Email's traces, the service on the page.** Every order's confirmation went through
`email/POST /send_order_confirmation`, and almost all of its time was `send_email`'s own, with the
template rendering beneath it done in a few milliseconds and nothing else beneath it at all. Email
was not waiting on anything. It was spending the time itself, after the email's content was
already rendered. Every one of those requests answered 200.

**Email's log.** Its request log said the same in seconds: each confirmation that completed took
0.28 to 1.14 seconds, against 0.002 to 0.04 before. And between them, again and again, the server
started up: `== Sinatra (v4.2.1) has taken the stage on 6060 for production with backup from
Puma`, then Puma's start-up banner. It started **30 times** in a little over nine minutes, 1 to 4
times a minute, each time after one or two confirmations, from 14 seconds after the trouble began.
Before none of those starts did email log anything: no error, no stack trace, no shutdown message.
A process that stops on an error of its own says so. One that is killed from outside does not.

**Checkout's errors.** Each was the same call: checkout's `HTTP POST` to email. Most ended in
`EOF`, email going away in the middle of answering; one was `connect: connection refused`, caught
while email was starting again and not yet listening. The orders around them went through: payment
and accounting kept their rates. Checkout does not fail an order when its confirmation fails, so
its errors stayed under the line. What checkout did do was wait: the confirmation call comes before
the order is published, and every order waited out email's half-second or more, which is
checkout's latency page. Confirmations sent fell from 5 to 10 a minute to between 3 and 7.

**Whether email was short of memory.** The tools can't say. Email reports no runtime series and no
memory metric, so its memory is not in the telemetry, and nothing in it records a kill either. Its
limit is 100M. What the telemetry does show is the shape of a memory kill: a process started over
and over, each time after one or two requests, with nothing logged before it went. The kill is
read from that pattern and the silence, not from a record. In the minutes before the trouble email
had not restarted at all.

**The sliver of flag errors.** A dead end. The same few services showed it before the trouble began
and again about ten minutes later, which is the flag service's routine stream reconnect, not a
second fault. It never came near a line, and neither email nor checkout was among them.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, and
no change to email's memory limit. The restarts were the runtime's, not anyone's change. So a
service that had been running steadily was now dying after every one or two requests, and each
request was taking tens to hundreds of times longer inside email's own code. Nothing about the
traffic had changed: the same few confirmations a minute. What each confirmation cost had changed,
and on this world what changes a service's behaviour without a deploy is a feature flag.

## Root cause

The `emailMemoryLeak` feature flag was set to its `10000x` variant in the flag service. With it
set, the email service stops discarding the confirmations it has sent and pads each one's body to
ten thousand times its length, about 19MB an email. The service filled its 100M limit within one or
two confirmations, was killed and restarted, and did so again every one or two confirmations for as
long as the flag was set. Each confirmation it managed to send took a quarter of a second or more
to build, and every order waited for it. The limit had not changed and nothing was deployed. The
fault was the flag's value.

## Resolution

The flag was set back to off. The flag service picks up the change on its own, so nothing was
restarted or redeployed by hand. Email's last restart came in the final seconds before the fix, and
none came after it. Email's p95 was back to 44ms within five minutes, as its window drained, and
confirmations picked up again, 74 in the five minutes after the fix. Checkout's latency alert
cleared about a minute and a half after the fix and email's about four and a half. Everything was
quiet 5m01s after the fix, and nothing fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back. Raising email's memory
limit would only have let it keep more.

## Detection notes

- Onset to first page: **4m16s**. Services on the page: **one**, email, the service whose code
  reads the flag. By the fix: **two**, with checkout waiting on it.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes.**
- Would the page alone have led you to the right service? **Yes, and not to what was wrong with
  it.** The page says slow. What was happening was a crash loop, and the page never says so.
- **A crash loop can page as latency and never as errors.** Email recorded no error span: a process
  that is killed leaves no span for the request it was serving. The failures showed up as the
  caller's `EOF` and `connection refused`, as fewer spans, and as the server starting over and over
  in its log.
- **A killed process has no last words.** Start-up banners with nothing logged before them mean the
  process was stopped from outside. Look for the memory limit.
- **A limit that is suddenly too small, when nobody changed it, means the service grew.** When a
  steady service starts dying after one or two requests of the same traffic, each request is
  costing more, and with nothing in change history, something changed what a request does without
  a deploy.
- **The caller's tolerance hides the victims.** Checkout completes the order when the confirmation
  fails, so its errors stayed under the line while confirmations went missing.
