---
id: service-productcatalogservice
title: Service - productcatalogservice
origin: authored
applies_to: [productcatalogservice]
signals: [ServiceHighErrorRate, ServiceHighLatency, ServiceNoTraffic]
actions: [restart_service, revert_config, rollback_image]
---

The most-called service in this world, and the one whose position most distorts a reader's
sense of how often it is at fault.

## What calls it

Three inbound edges, all **sync**, and the total dwarfs everything else:
`frontend -> productcatalogservice` (4575 calls), `recommendationservice ->
productcatalogservice` (444), `checkoutservice -> productcatalogservice` (451). Roughly 5470
calls against, for comparison, the 286 that reach emailservice.

No outbound edge in the measured graph.

## What the call volume does to the signals

The alert rules are **rate-based, not count-based** - error ratio over a two-minute window, p95
over the same. A busy service and a quiet one are held to the same threshold, so volume does
not make productcatalogservice alert more readily than anything else.

Where volume does matter is the other way round: **a rate computed over 4575 calls settles
quickly and a rate computed over 286 does not.** An error ratio here is a sharp measurement
within a window; the same ratio on a sparse service can take far longer to trip a rule, and
the catalog notes elsewhere that a sparse service is slower to page for exactly this reason.

## Reading an incident that names it

Three synchronous callers means a fault here surfaces in three places at once, and an incident
naming frontend, checkoutservice and recommendationservice together is the signature of
something they share rather than of three independent problems. Productcatalog is the most
common thing they share.

**And the converse.** Because it sits under three callers, it appears in the blast radius of
any of them - upstream traversal is transitive and it is one hop from frontend, one from
checkout, one from recommendation. Frequent appearance in a radius is a fact about the graph.

## Its silence

Better observed than most: three instrumented callers all page on their own behalf, so a
failure here is visible from three directions before it is visible here.
