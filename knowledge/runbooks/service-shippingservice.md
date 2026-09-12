---
id: service-shippingservice
title: Service - shippingservice
origin: authored
applies_to: [shippingservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

Shipping on the order path. `kind: application`, `tier: core`, owner `demo/checkout`, container
`shipping-service`. A Rust binary, and its container ceiling is sized for one.

## Its measured edges

| | edge | calls | kind |
|---|---|---|---|
| inbound | `checkoutservice -> shippingservice` | 572 | sync |
| outbound | `shippingservice -> quoteservice` | 286 | unmeasured |

One of the four services with an outbound edge in the measured graph, and its catalog
`depends_on` names the same callee. The inbound edge is `sync` by measurement - a bundle broke this
service and
checkoutservice's error ratio moved 0 → 0.227. The outbound one is `unmeasured`: no bundle has
ever broken quoteservice, so nothing recorded says what happens to shipping when it fails.

It logs incoming `GetQuoteRequest` at its ordinary rate, so its own logs record the calls it
makes across that edge.

## What it exports

Spans, `calls_total` and `latency_bucket` are all present, so all three alert rules can evaluate
for it. **Zero runtime-family series.** About **2,256 log lines an hour** at rest, which makes it
one of the more talkative services in this world.

## Its resting behaviour

p95 mean **12.35ms**, min 9.33, **max 39.0** over 181 samples of the clean 45-minute baseline -
the widest spread of any service outside the three with a measured at-rest tail. It records **zero
samples over the 250ms threshold** across a
twelve-hour census and it is **not** one of those three. Call rate mean 0.469 req/s.

Both figures are worth holding together: a service can have a wide resting spread and no tail at
all, and the two are measured by different statistics over different windows. **It also sits
outside the 1.9-9.7ms band that `service-cartservice` and `service-productcatalogservice`
quote**, for the same reason: that band is a median p95 over twelve hours, and 12.35ms is a mean
of p95 over 45 minutes.

**It has also been measured rising 2.7-2.9× in p95 while it was not a caller of the slowed
service.** Most likely contention on an emulated host, and recorded so nobody reads it as
evidence of a dependency edge.

## Its container ceiling

**120M, and it has never been raised.** The override sets it and has left it where it was while
several other limits moved; the figure is sized for a Rust binary's footprint rather than chosen
for headroom.

## Acting on it

`restart_service`, `revert_config` and `rollback_image` are all performable, each recreating the
container from its declared definition. Its one caller sees the connection reset while the
recreate runs; its callee does not, since an action here changes nothing on the other side of an
outbound edge.
