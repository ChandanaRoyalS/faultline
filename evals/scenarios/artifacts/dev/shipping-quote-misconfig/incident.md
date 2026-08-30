---
origin: scenario:shipping-quote-misconfig
split: dev
fault_class: bad_config
recorded_from: 2026-08-29T18:39:54+00:00
capability: cap:9c416e0a
onset_to_page: 2m49s
page_to_fix: 5m00s
fix_to_all_clear: 1m34s
---

# Checkout failed a quarter of its orders, and the service at fault reported nothing

## What was observed

The page named **checkoutservice**: `ServiceHighErrorRate`, 2m49s after the first failing
request. **loadgenerator** joined briefly. Nothing else alerted for the length of the incident.

Checkout's error ratio climbed to **27%** within a minute of the page and stayed between
**23% and 29%** until the fix — steady, not a spike, and about a quarter of every order placed.

## What was checked

**Checkout was failing, and checkout was fine.** Its own dependencies were all fast and all
succeeding: cart, product catalog, currency, payment, email and the order publish each completed
in single-digit milliseconds. A quarter of orders were failing and none of checkout's calls
were slow.

**The shipping service reported nothing at all.** No errors — its error ratio never left zero for
the entire incident, so it never appears in an error query and never came close to a rule. It is
not silent either: it logged an incoming `GetQuoteRequest` throughout, at its ordinary rate, right
through the window in which checkout was failing a quarter of its orders.

**And its logs never mention a failure.** This is the part worth carrying: shipping logs each
request it receives and writes nothing when it cannot service one. There is no error line, no
retry, no name of anything it failed to reach. Reading them tells you only that shipping was alive
and being asked for quotes — which is real evidence, and it is the evidence that rules out the
first thing anyone checks. It is not evidence of what went wrong.

**So no signal points at shipping.** Metrics say checkout. Logs say shipping is healthy. The
service that was misconfigured is invisible to both.

**Change history is what closed it.** Asked of checkout, it returns nothing in the window. Asked
of the services *around* the failure rather than the one alerting, it returns a configuration
change on shipping: the address it uses to reach the quote service was changed to one that does
not resolve. Nothing else changed anywhere.

## Root cause

Shipping's quote-service address was pointed at a host that does not exist. Shipping cannot price
a delivery, so every order that reaches the quote step fails — and it fails *upward*, into
checkout, which is where the errors appear and where the page came from.

## Resolution

The address was restored to its previous value.

## Detection notes

**The alerting service was not the faulty service, and nothing in the alert path could have said
so.** The whole page was about checkout. Checkout was healthy.

**A service can fail without reporting anything.** Shipping produced no errors and no error logs.
An investigation that treats "no errors here" as "nothing wrong here" clears it immediately and
correctly, and is then out of evidence.

**When the failing service's own history is empty, the question is not finished — it has moved.**
Correlating onset against changes *on the service that alerted* finds nothing here. The change
existed the whole time, on a service one hop away that never raised its voice.
