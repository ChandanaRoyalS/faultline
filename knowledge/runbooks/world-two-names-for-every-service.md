---
id: world-two-names-for-every-service
title: Two naming schemes, three label surfaces, and one canonical form
origin: authored
applies_to: [any]
signals: []
actions: []
---

The demo gives almost every service an explicit container name that is **not** its compose service
name: the service `cartservice` runs in the container `cart-service`. Anything that addresses this
world has to know which scheme it is speaking.

## Which mechanism picks which scheme

It is decided by the mechanism, not by the service. `docker update` and a traffic shaper address a
**container**; a compose override addresses a **service**. So the same service is `cart-service` to
one and `cartservice` to the other.

**Getting it wrong fails in two different unhelpful ways.** On a docker mechanism, `docker
inspect` says *no such container*. On a compose mechanism, the override declares a service the
base files do not have, and compose rejects the whole project with a message about an image or
build context - *the real target is untouched, and nothing in the message mentions the fault, the
override, or the fact that two naming schemes exist.*

## `canonical_service` is the only safe comparison

`"cart-service" == "cartservice"` is `False`. A check asking *do these two things touch the same
service* by comparing raw target strings **answers no for every pair that crosses the schemes -
silently, and in the direction that reports a contamination check as clean.**

**The compose service name is the canonical form**: it is what the world's own compose file keys
on, and every service has one, whereas a container name is only usually declared.

An unknown name is returned unchanged. **It is an identity function, not a validator** - a
separate check validates targets, and it runs at import.

## Eleven names are their own opposite

`alertmanager`, `frontend`, `grafana`, `jaeger`, `kafka`, `loki`, `prometheus`, `promtail`,
`quoteservice`, `redis-cart`, `tempo`. Those services can be addressed by either mechanism without
ambiguity.

Sixteen differ, and a few are not guessable: the feature-flag datastore is `ffs_postgres` as a
service and `postgres` as a container; the collector is `otelcol` and `otel-col`; the proxy is
`frontendproxy` and `frontend-proxy`; the load generator is `loadgenerator` and `load-generator`.

**The check is weakest exactly where the naming is least confusing**, since a self-identical name
passes under either convention.

## Three label surfaces, and they do not agree

| where | label | holds |
|---|---|---|
| span metrics (`calls_total`, `latency_bucket`) | `service_name` | the OTel `service.name` |
| runtime metrics (`process_runtime_*`, `runtime_*`) | `exported_job` | the **compose service** name |
| logs | `service` | the **container** name |

The dependency graph's node names are OTel `service.name` values and **agree with compose service
names in 12 of 13 cases**, which is why the capture has to be read through `canonical_service`
rather than compared directly. The measured log-volume figures are keyed by container name while
most other tables here use compose names.

## What the import-time check does and does not buy

It validates the **convention**, not existence: a definition naming a service passes whether or
not that service is running. And what it buys is **timing and phrasing, not detection** - both
wrong-convention mistakes already failed loudly, at injection time, in compose's or docker's
vocabulary rather than in this world's.

The map is a hand-maintained copy of naming that lives in a pinned clone this repository does not
own and cannot import from, with one accepted cost written down: **CI never clones that world, so
CI cannot catch naming drift** - only someone with it checked out will, which is also the only
person who could act on it.

Services behind a compose profile are deliberately absent from the map, because they are not part
of the world that starts, so nothing may target them.
