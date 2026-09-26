---
origin: scenario:v2-cart-flag-failure
split: dev
fault_class: feature_flag
recorded_from: 2026-09-26T20:17:03+00:00
capability: cap:d2b243e0
onset_to_page: 5m45s
page_to_fix: 5m00s
fix_to_all_clear: 2m01s
---

# A feature flag makes the cart fail to empty after an order

## What was observed

The page was one alert, `ServiceHighErrorRate` on **checkout**, 5m45s after the trouble started.
Nothing else fired, then or later, and nothing fired after the fix.

Checkout's error ratio had been zero. It rose from about a minute in and held at 7-8%. Its latency
rose too, from a p95 of about 30ms to between 110 and 160ms, without reaching the latency alert.
The storefront's latency followed it up a little, from about 38ms to about 60ms, and its error
ratio stayed at **zero**. So did frontend-proxy's and the load generator's. Payment, email and
accounting kept their usual traffic: orders were being charged, confirmed and recorded at the
normal rate.

That is the puzzle on the page: checkout erroring on 7-8% of its spans while every order it was
asked to place went through.

## What was checked

**Checkout's error traces, to see which of its calls failed.** Every order completed: the cart
read, the product lookups, the currency conversions, the shipping quote, the payment and the
confirmation email all succeeded, and `PlaceOrder` itself did not error. One call in each order
failed: `checkout/oteldemo.CartService/EmptyCart`, the last step, which clears the customer's cart
once the order is placed. Its error was `Can't access cart storage. System.ApplicationException:
Wasn't able to connect to redis`. Checkout does not treat that as an order failure, which is why
the orders succeeded and why the storefront saw nothing.

**How long it took.** Between about 60 milliseconds and five seconds. In one order `EmptyCart`
held the order open for 5.1 seconds before failing, and the confirmation email went out only after
it. That is checkout's latency rise: its orders were waiting on a call that was going to fail.

**The cart, where the error came from.** Cart's own `EmptyCart` span was in error with the same
message, `FailedPrecondition`, `Can't access cart storage`. Beneath it was a single call, to the
flag service, a feature-flag lookup, and then nothing: no call to the cart store at all. In the
same traces, cart's `GetCart` ran its store query, `HGET`, and answered in about a millisecond.

**Its log.** Cart logged each `EmptyCartAsync called with userId=...`, followed within a second by
`fail: ... Wasn't able to connect to redis` and the gRPC server's `Error status code
'FailedPrecondition'`, 4 to 12 of these a minute, one for every `EmptyCart` from the start until
the fix, and none before or after. Its `AddItemAsync` and `GetCartAsync` lines went on at their
usual rate beside them.

**Whether the cart's store was down.** This is where the log points, and it was not. "Wasn't able
to connect to redis" reads like the cart's Valkey store is unreachable. But in the same minutes
cart was adding items and reading carts through that store without an error, and its store queries
answered in a millisecond. The store has no telemetry of its own the tools can read, so its health
shows only through cart's calls to it, and those were fine. Something that could reach the store
for two operations and not for the third was not failing on the store. It was going somewhere else
for the third.

**Whether cart was struggling.** It was not. Its error ratio rose only to about 4.5%, because
`EmptyCart` is about one call in ten to cart and its other spans stayed clean, so cart itself never
paged. Its .NET runtime series, 39 of them, reported without a gap, and its latency rose only
slightly.

**What changed.** Nothing, as far as change history shows: no deploy, no configuration change, no
restart. The one thing in the failing span besides the error is the feature-flag lookup made just
before it, on the only operation that failed.

## Root cause

The `cartFailure` feature flag was turned on in the flag service. With it on, cart's `EmptyCart`
switches to a second store configured with an address that does not exist, tries to connect, and
fails. Adding to carts and reading them keep using the real store and keep working. Checkout
empties the cart after every placed order and ignores that call's failure, so every order
completed, each one slowed by the failing call and each customer's cart left full afterwards.
Checkout paged on the errors of a call it does not act on. Nothing was deployed or reconfigured,
and the cart's store was healthy. The fault was the flag's value.

## Resolution

The flag was turned back off. The flag service picks up the change on its own, so nothing was
restarted or redeployed. `EmptyCart` went back to the real store and succeeded at once, and the
error ratios drained with their windows. Everything was quiet 2m01s after the fix, and nothing
fired during recovery.

Class of fix: **config_revert**. One setting was wrong and it was set back.

## Detection notes

- Onset to first page: **5m45s**. Services on the page: **one**, checkout, which was not at fault.
  By the fix: **one**.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** Checkout paged on its calls to cart.
  Cart, where the flag acts, stayed under the line at 4.5%.
- Would the page alone have led you to the right service? **No, but the traces do in one step.**
  Checkout's error traces all fail at the same call, `EmptyCart`, and nowhere else.
- **An error ratio can rise while nothing fails for the user.** Checkout's orders all went through.
  The errors were on a clean-up call it does not act on. Check what the failing span is before
  reading a caller's error ratio as a failure rate.
- **"Can't connect to the store" is not proof the store is down.** The same service was using the
  same store for its other operations in the same minute. A failure confined to one operation
  points at something that operation does differently.
- **Look at what the failing span did instead.** It made a feature-flag lookup and never reached the
  store. With nothing in change history, a flag evaluated on exactly the failing path is the change
  to look at.
