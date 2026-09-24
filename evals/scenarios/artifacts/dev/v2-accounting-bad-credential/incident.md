---
origin: scenario:v2-accounting-bad-credential
split: dev
fault_class: bad_config
recorded_from: 2026-09-24T17:53:56+00:00
capability: cap:d2b243e0
onset_to_page: 4m16s
page_to_fix: 5m00s
fix_to_all_clear: 4m01s
---

# Accounting's database password rotated to one the database does not accept

## What was observed

The page was a single alert, `ServiceHighErrorRate` on **accounting**, 4m16s after the
trouble started. Nothing else fired then, and nothing else fired afterwards. Its error
ratio had no series at all before the incident, because accounting had not recorded an
error in the window. It appeared a little over two minutes in, climbed, and settled at
**exactly one third** of its spans once the rate window filled. It held there, flat, until
the fix.

Nothing around accounting moved. Its own request rate held at its usual level, a little
under half a request a second, and its latency did not change. Checkout was placing orders
at about its usual rate, with no change in latency. The storefront showed nothing, and neither did the other
services that read and write the same database.

## What was checked

**Whether accounting was down, restarting or starved.** It was not. Its .NET runtime series
never dropped out, and it kept taking orders off the topic at the rate it always does. A
service that pages on errors while its traffic and latency look normal is one that is
running and failing at something specific. The container had been recreated at the start
of the incident, and it was running normally since.

**Its logs, first over the whole incident.** That showed nothing wrong. The log tool returns
the oldest and newest lines of a window, and both ends were ordinary `Order details` lines:
the start before the trouble, the end after the fix. The failures were all in the middle it
does not return. Narrowed to the minute after the start, the log was unambiguous. Every order
accounting received was followed by `fail: Accounting.Consumer … Order parsing failed:`
wrapping `Npgsql.PostgresException: 28P01: password authentication failed for user "otelu"`,
about forty lines of stack trace per order. Every order in that minute failed the same way,
and none before it had.

**The "Order parsing failed" label.** It reads like a malformed message on the orders topic,
something checkout started producing, and that is the dead end it invites. The other
consumer of the same topic answered it: fraud-detection read the same orders throughout with
no change in its errors or latency. The messages were fine. The label is the consumer's
catch-all, and the exception inside it is the real error.

**The database.** Postgres was up and serving. product-catalog and product-reviews, which use
the same database, showed no change in errors or latency. The database was healthy and one
client could not get in.

**The traces.** Each order is three spans: `order-consumed`, `orders receive`, and a `CONNECT
otel` to the database. The connect span was the error, and its status read `28P01`, the
Postgres code for a failed password authentication. The consumer span around it did not
error. That is also the one-third: one span of three fails on every order, so an error ratio
of exactly 0.333 means every order was failing, not a third of them.

**Its runtime counters.** `PostgresException` in the .NET exception counter climbed at about two
a second through the incident, from almost none before it. That is many times the rate orders
arrive, so each failure is counted more than once on its way up.

**What changed.** One record, at the start: `DB_CONNECTION_STRING updated on accounting`. That is
the credential the failing connect span uses.

## Root cause

Accounting's database connection string was changed to a password the database does not
accept. Postgres itself was healthy and every other client of it was unaffected. Accounting
kept consuming orders as normal, and every attempt to write one failed at authentication,
before any query ran. Nothing upstream waits on accounting, so nothing upstream noticed.

## Resolution

The connection string was set back to the working password and accounting was recreated
with it. The orders that arrived while it was being replaced were picked up together a
few seconds after it came back, and wrote normally. The error ratio drained with its
five-minute window, and the alert cleared 4m01s after the fix. Nothing fired during
recovery.

Class of fix: **config_revert**. Nothing was deployed and no code was wrong. One
configuration value was wrong, and it was set back.

## Detection notes

- Onset to first page: **4m16s**. Services on the page: **one**. By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **Yes**, and it was the only one. A
  failure in a pure consumer stays where it is, because nothing calls it and nothing waits
  on it.
- Would the page alone have led you to the right service? **Yes, but not to the cause.** The
  cause was in three places, none on the page: the log line inside a misleading label, the
  connect span's status code, and the change record.
- **An error ratio of exactly one third is a count, not a severity.** It is one failing span
  per three-span order. Read as "a third of orders fail", it undersells a total failure.
- **A log query over the whole incident showed only healthy lines.** Both ends of the window
  were fine; the failures filled the middle. Narrow the window to the start before
  concluding that a service's log is clean.
- **Authentication refused is not connection refused.** A wrong host or port fails at the
  socket, with no Postgres error code. `28P01` means the database was reached and said no,
  which points at the credential and away from the network.
