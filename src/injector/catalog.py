"""The fault definitions the injector ships with (T1.4).

Defaults are chosen to produce failures this world has been observed to
produce, against thresholds T1.3 measured on a healthy baseline - a fault that
trips no alert teaches the investigator nothing, and one that flattens the
world teaches it nothing either.

Note which name each fault targets. Faults that reach containers directly
(docker update, tc netem) target the *container* name; faults that go through
compose target the *service* name. The demo names them differently on purpose
(service `cartservice`, container `cart-service`), so they are not
interchangeable. That is checked here rather than left to the reader: importing
this module validates every definition against the world's naming, so a fault
using the wrong convention fails loudly at import instead of at 2am (ADR-0011).
"""

from __future__ import annotations

from evalharness.scenario import FaultClass
from injector.faults import target_kind
from injector.models import FaultDefinition, TargetKind
from injector.world import CONTAINER_SERVICES, SERVICE_CONTAINERS


class CatalogError(RuntimeError):
    """A shipped fault definition cannot be right, so the injector refuses to load."""


def check_target(definition: FaultDefinition) -> None:
    """Raise unless `target` uses the naming convention this definition's mechanism needs."""
    kind = target_kind(definition)
    wanted, other = (
        (SERVICE_CONTAINERS, CONTAINER_SERVICES)
        if kind is TargetKind.SERVICE
        else (CONTAINER_SERVICES, SERVICE_CONTAINERS)
    )
    if definition.target in wanted:
        return

    expected = "a compose service name" if kind is TargetKind.SERVICE else "a container name"
    # The common mistake is reaching for the world's *other* name for the same
    # thing, so when that is what happened, say which one to use instead of
    # leaving the reader to work out that the two naming schemes exist.
    correction = other.get(definition.target)
    detail = (
        f"is the world's other name for the same thing - use {correction!r}"
        if correction is not None
        else "is not a name in the world injector.world describes"
    )
    raise CatalogError(
        f"{definition.id}: {definition.fault_class} addresses {expected}, "
        f"but {definition.target!r} {detail}"
    )


def _validated(definitions: tuple[FaultDefinition, ...]) -> tuple[FaultDefinition, ...]:
    for definition in definitions:
        check_target(definition)
    return definitions


CATALOG: tuple[FaultDefinition, ...] = _validated(
    (
        FaultDefinition(
            id="recommendation-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="recommendation-service",
            description=(
                "Shrink the recommendation service's memory limit below its working set. "
                "The kernel OOM-kills it, compose restarts it, and the frontend sees the gap."
            ),
            # 32m, and the reason is recovery time rather than severity. 48m is already
            # below the ~55MiB steady-state RSS and kills the container about every 36
            # seconds - but a Python process restarts in a second or two, faster than the
            # 15s scrape, so a full 12-minute rehearsal produced 49 of 49 samples present,
            # no gaps, no errors and no alert. The fault fired constantly and was
            # invisible. 32m is below what the runtime needs to finish starting at all:
            # the container is OOM-killed before startup completes, never reaches a
            # serving state, and `docker ps` reports Restarting (137). The service is then
            # genuinely absent rather than briefly away, which is what makes it
            # observable. See CATALOG.md for the 48m measurement.
            params={"memory": "32m"},
        ),
        FaultDefinition(
            id="cart-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="cart-service",
            description=(
                "Shrink the cart service's memory limit below its working set. A .NET service "
                "rather than the JVMs the other two squeezes target, which is the point: its GC "
                "reads the cgroup limit and may respond by collecting harder instead of dying."
            ),
            # NO SCENARIO USES THIS. T7.20 probed it at two magnitudes and it failed the
            # alerting gate at both, for different reasons - kept because the measurement is
            # worth reproducing, not because a scenario is coming.
            #
            # At 200m the container is killed and restarted (RestartCount 0->1, then 1->2->3
            # on the second attempt; .NET's gc_collections counter resets, which is how the
            # restart is visible) and **nothing alerts**: zero errors on every service, cart
            # p95 flat at 1.9ms, across two seven-minute attempts. The restart is faster than
            # detection. Exactly the shape recorded for recommendation-memory-squeeze at 48m.
            #
            # At 32m it is OOM-killed before startup completes - 16 restarts in seven minutes,
            # never reaching a serving state - and alerts far too much: eleven, including
            # ServiceNoTraffic on seven services. Worse for the catalog, cartservice's runtime
            # metrics **disappear while the fault is live** (heap and gc go null), so the
            # evidence class the scenario passed T7.5's reachability gate on does not exist
            # under its own fault. And it is then hard to tell from cart-bad-image-tag.
            params={"memory": "200m"},
        ),
        FaultDefinition(
            id="shipping-quote-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="shippingservice",
            description=(
                "Point the shipping service at a quote service that does not resolve. A third "
                "bad_config shape: a broken service-to-service address rather than a wrong "
                "backing store or a wrong flag."
            ),
            # The real value is http://quoteservice:8090.
            #
            # T7.20 probed the open alerting gate twice and it PASSES, reproducibly:
            # ServiceHighErrorRate/checkoutservice fires at T+240s in both attempts, with
            # checkout's error ratio holding 24-28%.
            #
            # The answer to the question the gate was open on: a failed GetQuote does **not**
            # surface as an error at shippingservice - its own error rate stays 0.000 for the
            # whole fault. It surfaces at its *caller*. So the alerting service is not the
            # faulty one, and shipping looks clean by error rate; the only class that reaches
            # it is its logs, which is the one class T7.4's census gives it.
            params={"env_var": "QUOTE_SERVICE_ADDR", "value": "http://quoteservice-gone:8090"},
        ),
        FaultDefinition(
            id="storefront-load-surge",
            fault_class=FaultClass.BAD_CONFIG,
            target="loadgenerator",
            description=(
                "Raise the offered load fiftyfold. Nothing in the storefront is changed or "
                "broken - the shops simply get more customers than they can serve, which is "
                "what separates a scale fault from a resource-exhaustion one."
            ),
            # 500 users against the world's default 10. The mechanism is BAD_CONFIG only
            # because setting an environment variable is how the load driver is steered;
            # the *scenario* built on it is not a misconfiguration, and its ground truth
            # says so. `LOCUST_USERS=500` is a legitimate value that breaks no invariant.
            #
            # T7.13 MEASURED THIS AND IT DOES NOT ALERT. 50x offered load holds the world
            # at a 102 req/s throughput plateau for 20 minutes with no rule tripping: the
            # scenario built on it carries `blocked: true` and the numbers are in ADR-0024.
            # The definition is kept because the fault is real and injectable - what it is
            # not is observable through this world's alert path.
            params={"env_var": "LOCUST_USERS", "value": "500"},
        ),
        FaultDefinition(
            id="flag-service-bad-deploy",
            fault_class=FaultClass.BAD_DEPLOY,
            target="featureflagservice",
            description=(
                "Deploy a build of the flag service whose GetFlag returns UNAVAILABLE. It starts "
                "and serves, then fails on the hot path - the cascade to recommendationservice "
                "and the frontend that ADR-0006 measured."
            ),
            params={"image": "ffs-stub:2", "server": "server_v2.py"},
        ),
        FaultDefinition(
            id="flag-service-crashloop",
            fault_class=FaultClass.BAD_DEPLOY,
            target="featureflagservice",
            description=(
                "Deploy a build of the flag service that serves correctly and then exits. The "
                "world restarts it, so it flaps rather than failing or staying down - callers "
                "see bursts of UNAVAILABLE between healthy stretches, and the restart count is "
                "the only signal that names the cause."
            ),
            # The third shape of a bad deploy, and the point of having three: this is
            # neither flag-service-bad-deploy (starts, then fails every call) nor
            # cart-bad-image-tag (never starts). An agent that has learned "bad_deploy
            # means steady 5xx" should get this one wrong.
            params={"image": "ffs-stub:3", "server": "server_v3.py"},
        ),
        FaultDefinition(
            id="ad-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="ad-service",
            description=(
                "Add 300ms of network delay to the ad service. The frontend's ad panel slows "
                "while the storefront keeps serving - a second dependency_latency target, on "
                "the best-instrumented service in the world."
            ),
            # NO SCENARIO USES THIS. T7.22 injected it and measured it invisible: 900s of
            # alert budget plus 300s of steady state, and adservice p95 never left 1.9ms. No
            # rule fired. Kept because the measurement is worth reproducing.
            #
            # `tc netem` delays egress, and adservice is a leaf - it serves ads from memory and
            # calls nothing - so its delayed egress lands after its server span has closed and
            # never enters its own span metrics. cartservice moves to ~650ms under the identical
            # mechanism because it makes downstream calls whose delayed egress extends its span.
            #
            # The magnitude is not the problem and lowering or raising it will not help: the
            # target has no downstream call for the delay to sit inside.
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="cart-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="cart-service",
            description=(
                "Add 300ms of network delay to the cart service, well past the 250ms p95 alert "
                "threshold, so checkout slows without anything erroring outright."
            ),
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="currency-cpu-throttle",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="currencyservice",
            description=(
                "Cut the currency service's CPU quota to a sliver. Every price on every page "
                "goes through it, so conversions queue behind the CFS period and latency climbs "
                "across the storefront while nothing errors outright."
            ),
            # 0.05 CPU = 5ms of runtime per 100ms period. The currency service is a
            # small C++ gRPC server whose per-call work is short, so a quota set
            # *above* its average demand would never throttle; one set far below it
            # would queue without bound until callers time out and the fault becomes
            # an error-rate incident instead of a latency one. 0.05 sits close to the
            # measured demand on purpose, so the container exhausts its slice inside
            # most periods and stalls to the next one - tens of ms at a time, which is
            # what pushes p95 past the 250ms alert without breaking anything.
            # NOT YET REHEARSED: see ADR-0010. If p95 stays under 250ms, halve it; if
            # ServiceHighErrorRate fires instead, raise it.
            params={"cpus": "0.05"},
        ),
        FaultDefinition(
            id="ad-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="ad-service",
            description=(
                "Shrink the ad service's memory limit below its JVM working set. The heap was "
                "sized for the old ceiling, so the kernel OOM-kills it and the frontend loses "
                "its ad panel while everything else keeps serving."
            ),
            # 256m against the 700M ceiling world-arm64.override.yml gives it. That
            # ceiling was itself raised from the demo's native-x86 300M because the
            # JVM sits at its limit under emulation, so the working set is known to be
            # north of 300M and 256m cannot hold it. `docker update` moves the cgroup
            # limit under a JVM that already sized its heap for 700M, which is what
            # makes the kill prompt rather than eventual.
            params={"memory": "256m"},
        ),
        FaultDefinition(
            id="frauddetection-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="frauddetection-service",
            description=(
                "Shrink the fraud detection service's memory limit below its working set. "
                "It consumes from Kafka and nothing calls it synchronously, so it dies "
                "without anything upstream noticing - the storefront never changes."
            ),
            # 200m against a 500M ceiling and a measured resting usage of 326MiB, so the
            # limit lands well below the working set rather than merely removing headroom.
            #
            # A JVM on purpose. ad-memory-squeeze established that this mechanism kills a
            # JVM outright and that the restart is slow enough to leave a visible gap;
            # recommendation-service at 48m proved a fast-restarting Python process is
            # killed just as often and stays invisible (CATALOG.md). Runtime choice is the
            # variable that decides whether this mechanism produces a signal at all.
            params={"memory": "200m"},
        ),
        FaultDefinition(
            id="cart-bad-image-tag",
            fault_class=FaultClass.BAD_DEPLOY,
            target="cartservice",
            description=(
                "Deploy the cart service on an image tag that was never pushed. The container "
                "never starts, so cart goes dark rather than erroring: ServiceNoTraffic is the "
                "alert that names the culprit, and the callers' errors are downstream noise."
            ),
            # A plausible hotfix tag against the world's real image name, so the
            # investigator has to notice the tag is wrong rather than that the image
            # is obviously foreign. No `server` param, so nothing is built; expect_start
            # "no" because the point is that this tag resolves nowhere.
            params={
                "image": "ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2",
                "expect_start": "no",
            },
        ),
        FaultDefinition(
            id="email-wrong-image",
            fault_class=FaultClass.BAD_DEPLOY,
            target="emailservice",
            description=(
                "Deploy the quote service's image into the email service's slot. The image "
                "resolves and the container is created, then Apache cannot configure "
                "itself because a variable it needs is not in this service's environment, "
                "and it crash-loops."
            ),
            # Probed for five minutes, not a full rehearsal. Measured: the container
            # starts, Apache fails to configure because QUOTE_SERVICE_PORT is not defined
            # in emailservice's environment, and it crash-loops with exit 1.
            # ServiceHighErrorRate fired on checkoutservice within five minutes.
            #
            # Exit 1 with a configuration error in the logs, not exit 137 - which is what
            # separates this from shipping-wrong-image, where the same class of mistake
            # produces a resource signature that points at the wrong fault class. Here the
            # logs name the cause outright. See CATALOG.md on the bad_deploy trio.
            params={
                "image": "ghcr.io/open-telemetry/demo:v1.2.1-quoteservice",
                "expect_start": "yes",
            },
        ),
        FaultDefinition(
            id="shipping-wrong-image",
            fault_class=FaultClass.BAD_DEPLOY,
            target="shippingservice",
            description=(
                "Deploy the ad service's image into the shipping service's slot. The image "
                "resolves and the deploy succeeds, so this is a release that shipped - but "
                "a JVM does not fit a container sized for Rust, and it is OOM-killed "
                "before it can serve."
            ),
            # Measured: the JVM starts, the OTel agent loads, then exit 137 in a restart
            # loop. shippingservice's ceiling is 120 MiB, sized for a Rust binary; the ad
            # service is a JVM and needs several times that.
            #
            # The image was chosen for exactly that mismatch. A wrong image that merely
            # served the wrong protocol would look like a config or dependency fault; a
            # wrong image that is a *heavier runtime than the slot was sized for* fails
            # with a resource signature - exit 137, OOMKilled, restart loop - which is
            # indistinguishable from a memory-limit fault and has a different remediation.
            # That is the point of the scenario. See CATALOG.md.
            params={
                "image": "ghcr.io/open-telemetry/demo:v1.2.1-adservice",
                "expect_start": "yes",
            },
        ),
        FaultDefinition(
            id="productcatalog-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="product-catalog-service",
            description=(
                "Add 300ms of network delay to the product catalog service. It sits on the "
                "product listing and the checkout path both, so the slowdown shows up in two "
                "places at once and the shared dependency is the thing to find."
            ),
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="cart-redis-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="cartservice",
            description=(
                "Point the cart service at the wrong Redis port. The dependency is up, the "
                "config is wrong, and only cart operations fail - a config-revert, not a rollback."
            ),
            params={"env_var": "REDIS_ADDR", "value": "redis-cart:6380"},
        ),
        FaultDefinition(
            id="payment-telemetry-blackout",
            fault_class=FaultClass.BAD_CONFIG,
            target="paymentservice",
            description=(
                "Repoint the payment service's OTLP *trace* exporter at a dead address. The "
                "service keeps serving and keeps processing payments; only its spans stop. "
                "`calls_total` is built from those spans by the collector's spanmetrics "
                "connector, so the traffic metric drains to zero and `ServiceNoTraffic` fires on "
                "a service that is working perfectly - a config-revert, not a restart."
            ),
            # **Traces only, and the metrics endpoint is deliberately left alone.** It is a
            # separate variable, so `app_payment_transactions` keeps incrementing and stays
            # reachable to a live promql query during the incident.
            #
            # **It is not the bundle's discriminator, and the first draft of this comment said
            # it was.** `runtime.json` captures only `RUNTIME_FAMILIES`, and a business counter
            # is not one; paymentservice exports no runtime family at all, so that capture reads
            # empty on a healthy recording too. **The discriminator in the bundle is the logs**:
            # 111 "Charge request received." lines across the fault window at T7.36, steady
            # through every minute the alert was firing. Logs travel by promtail over the docker
            # socket and no OTLP setting can silence them.
            #
            # 127.0.0.1:4317 inside the container has nothing listening, so the exporter fails
            # fast and drops spans rather than blocking the request path - measured at T7.36:
            # checkout error ratio stayed 0.0 for the whole fault window.
            params={
                "env_var": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                "value": "http://127.0.0.1:4317",
            },
        ),
        FaultDefinition(
            id="checkout-currency-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="checkoutservice",
            description=(
                "Point the checkout service at a currency host that does not exist. Currency "
                "itself is healthy and serving everyone else, so only checkout fails - the "
                "evidence is in the caller's config, not in the dependency."
            ),
            # A hostname in the shape the world's own addresses take, resolving nowhere
            # on the compose network. The port stays 7001 so the wrong thing is the
            # host, and only the host.
            #
            # No scenario cites this fault at n=10. It is a near-duplicate of
            # cart-redis-misconfig - a service pointed at an address that does not
            # answer - and bad_config has two slots for three faults (ADR-0008).
            # Kept as the T7.1 spare: do not delete it to tidy the gap.
            params={"env_var": "CURRENCY_SERVICE_ADDR", "value": "currencyservice-canary:7001"},
        ),
        FaultDefinition(
            id="product-catalog-flag-failure",
            fault_class=FaultClass.BAD_CONFIG,
            target="featureflagservice",
            description=(
                "Turn on the demo's own productCatalogFailure flag at the flag service. "
                "GetProduct starts failing for one product id, so the product catalog errors "
                "on part of its traffic and the cause is a flag, not the service's own code."
            ),
            # The stub answers every flag "disabled" unless FAULTLINE_ENABLED_FLAGS
            # names it (ADR-0006, ADR-0010). productCatalogFailure is read by
            # productcatalogservice itself - see world/src/productcatalogservice/main.go -
            # so this is the demo's designed failure mode, driven from config rather
            # than from a rebuilt image.
            params={"env_var": "FAULTLINE_ENABLED_FLAGS", "value": "productCatalogFailure"},
        ),
    )
)


def by_id(fault_id: str) -> FaultDefinition | None:
    return next((f for f in CATALOG if f.id == fault_id), None)
