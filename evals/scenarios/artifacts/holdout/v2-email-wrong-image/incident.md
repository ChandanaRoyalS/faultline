---
origin: scenario:v2-email-wrong-image
split: holdout
fault_class: bad_deploy
recorded_from: 2026-09-27T08:06:47+00:00
capability: cap:d2b243e0
onset_to_page: 5m02s
page_to_fix: 5m00s
fix_to_all_clear: 3m01s
---

# Email deployed with another service's image

## What was observed

The page was one alert, `ServiceHighErrorRate` on **checkout**, 5m02s after the trouble started.
Three minutes later `ServiceNoTraffic` fired on **email**. Nothing else fired, then or later, and
nothing fired after the fix.

Checkout's error ratio had been zero. It was half a percent a minute in, 2.3% at two minutes, 5.1%
at three, 6.6% at four, and from five minutes it held at 7.4-7.5% for as long as the trouble
lasted. Its latency did not rise. It eased, from a p95 of 31-34ms to 25-28ms, and its request rate
held at its usual two spans a second. The storefront did not move at all: the frontend,
frontend-proxy and the load generator recorded no errors and no change in latency. Payment,
accounting and fraud-detection kept their usual rates, so orders were being placed, charged and
recorded as before. Nothing behind checkout went quiet except email, whose span rate fell from
about 0.6 a second to 0.45 a minute in, 0.15 at three minutes and nothing from five, with no error
of its own and, from then on, no latency value at all.

That is the page: checkout erroring on about one span in fourteen while every order it was asked
to place went through.

## What was checked

**Checkout's error traces, the service on the page.** Every one had the same shape, 84 of them over
the ten minutes, one for each order. `oteldemo.CheckoutService/PlaceOrder` succeeded. Beneath it the
cart read, the product lookups, the currency conversions and the shipping quote all succeeded;
payment's `Charge` succeeded; the shipment and the emptying of the cart succeeded; and then
checkout's `HTTP POST` to email failed with `dial tcp: lookup email on 127.0.0.11:53: no such
host`, with nothing beneath it, in about 2ms. After it, the order was still published. One failing
call at the end of an order that completed. The trouble was not in checkout's work. It was in the
one service checkout could no longer find.

**Whether orders were completing.** They were, 85 of them over the fault, and all but one of those
completed orders carried the error: the same traces. Checkout does not fail an order when its
confirmation email fails; it records the failure and publishes the order. That is why its error
ratio stopped at 7.5%, the email call's share of an order's spans, and why nothing behind it went
quiet.

**Email itself.** It produced no span at all during the fault. Its traffic did not fall to a
failing level; it fell to zero, and that is what paged on it, once its five-minute window had
drained. Email has no runtime series to say whether its process was up. Its log said instead, and
what it said was not email's. At the moment the trouble began, the old server stopped cleanly -
`Gracefully stopping, waiting for requests to finish`, `== Sinatra has ended his set` - and then,
where Sinatra's request lines had been, a PHP stack trace:

`Fatal error: Uncaught InvalidArgumentException: Invalid URI "tcp://0.0.0.0:" given (EINVAL) in
/var/www/vendor/react/socket/src/TcpServer.php:161`, three frames, the last of them
`/var/www/public/index.php(102): React\Socket\SocketServer->__construct('0.0.0.0:')`.

The same seven lines **19 times** in ten minutes and nothing else: six in the first three seconds,
then the gaps growing - 4, 6, 13, 26, 52 seconds - to once a minute, the last of them fifteen
seconds before the fix. That is a container that dies as it starts and a runtime backing off
between attempts. Email is a Ruby service and does not run PHP. The program in its slot was trying
to listen on an address with no port, because the variable that would have supplied one was never
part of email's environment, and it said so every time it ran.

**Why "no such host".** A container that is not running has no address on the network. Between
its short-lived starts there was nothing for checkout to resolve, so the failure was the name
rather than a refused connection, and it cost checkout about 2ms rather than a wait.

**Whether email was short of memory.** No. A process killed at its limit leaves no last words; this
one wrote its own reason, the same reason, before every exit. Its limit is 100M and the tools have
no memory series for it, but the log rules the limit out: the process never got as far as serving.

**The storefront.** The frontend logged nothing new through the fault, because nothing it asked for
failed. Order confirmations are not something a shopper waits on.

**The flag readers' sliver.** A dead end. Fraud-detection and flagd showed error ratios of 1.4-1.6%
and under 1% for a few minutes around two and again around twelve minutes in, and had shown the
same five minutes before the trouble began: the flag service's routine ten-minute stream reconnect.
It came nowhere near a line and involved no order.

**What changed.** One record, at the start: `image reference updated on email`, to
`ghcr.io/open-telemetry/demo:2.2.0-quote`. That is the quote service's image. The deploy had
worked - the image exists and the container was created - and what it ran was the wrong program.
Nothing else had changed: email's memory limit and environment were what they had always been, and
nothing had changed on checkout or anywhere else.

## Root cause

A deploy put the quote service's image into email's slot. The image resolved, so the deploy
succeeded, but what it started was the quote service's PHP server, which binds to a port named by
a variable email's environment does not set. It died with a fatal error on every start, 19 times,
with the runtime backing off between them, and never served a request. Every order's confirmation
failed at checkout's call to email, after the order had been charged and shipped, and checkout
completed the orders anyway. Nothing was wrong with email's limit, with checkout or with any other
service.

## Resolution

Email was rolled back to its own image, `2.2.0-email`. Sinatra was listening two seconds after the
fix and sent its first confirmation two seconds after that, 59 in the five minutes after the fix
against 56 in the five before. Email's no-traffic alert cleared within a minute of the fix and
checkout's error alert two and a half minutes after it, as its window drained. Everything was quiet
3m01s after the fix, and nothing fired during recovery.

Class of fix: **rollback**. A deploy was wrong and it was undone. Restarting email was what the
runtime had already been doing, 19 times; raising its limit would have changed nothing, because
the process never reached it.

## Detection notes

- Onset to first page: **5m02s**. Services on the page: **one**, checkout, which was not at fault.
  By the fix: **two**, email among them.
- Alerts that fired only during recovery: **none**.
- Did the loudest service turn out to be the culprit? **No.** Checkout paged on its calls to email;
  email's only alert was the absence of traffic, three minutes later.
- Would the page alone have led you to the right service? **No, but one trace does.** Every order
  has one failing span, and it is the call to email.
- **An error ratio that holds at one span's share means every request fails at the same step and
  completes anyway.** Checkout's 7.5% was not one order in fourteen failing; it was every order
  losing its confirmation. Read the shape before reading the number.
- **A caller's tolerance hides the victim.** The storefront never moved and no service went quiet
  but email, because checkout carries on without a confirmation. The fault was invisible to
  shoppers and nearly invisible to alerting.
- **A log in the wrong language is the whole story.** Email does not run PHP. A stack trace where
  Sinatra's request lines had been means something else is running in its place, and this one
  named what it was missing.
- **A process that reports its own error was not killed.** Start-up banners with nothing before
  them mean a kill; a fatal error before every exit means the program could not run as
  configured. The first points at a limit, the second at the program, and the change record says
  which program.
- **"No such host" from a caller means the callee has no address, not that the name was wrong.**
  Between a crash-looping container's starts, its name resolves to nothing.
