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
from injector.world import container_services, service_containers


class CatalogError(RuntimeError):
    """A shipped fault definition cannot be right, so the injector refuses to load."""


def check_target(definition: FaultDefinition) -> None:
    """Raise unless `target` uses the naming convention this definition's mechanism needs."""
    kind = target_kind(definition)
    services = service_containers(definition.world)
    containers = container_services(definition.world)
    wanted, other = (services, containers) if kind is TargetKind.SERVICE else (containers, services)
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
            id="redis-cart-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="redis-cart",
            description=(
                "Add 300ms of network delay to the cart service's Redis, not to the cart "
                "service. Cart's handler blocks waiting for responses that are late, so cart "
                "looks slow while the thing that is slow has no spans, no service-level "
                "metrics and no name anywhere in the traced graph."
            ),
            # **The target is the datastore, and that is the whole point.** The container needs
            # no `tc` and no NET_ADMIN: pumba runs tc from a sidecar image into the target's
            # network namespace, so redis-cart stays the image the world pins. It has an eth0.
            #
            # This is a *container* target, like cart-service above and unlike the service-named
            # bad_config targets - redis-cart is not in SERVICE_CONTAINERS because it is not a
            # traced service, which is precisely what makes it interesting here.
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
            id="accounting-kafka-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="accountingservice",
            description=(
                "Point the accounting service's Kafka broker address at a port nothing listens "
                "on. **The first fault in this catalog that breaks a consumer rather than a "
                "server.** Nobody calls accountingservice, so it cannot have an error rate and "
                "cannot have latency; the only signal it can produce is absence - and absence is "
                "already produced by an OOM kill (frauddetection-memory-squeeze) and by a broken "
                "telemetry path (payment-telemetry-blackout) from two other causes. This is the "
                "third: alive, unrestarted, and consuming from nowhere."
            ),
            # **MEASURED AT T7.56 AND IT DOES NOT PRODUCE A SCENARIO.** The mechanism works
            # perfectly - the override is applied, the container is recreated, the address takes
            # effect. What fails is the premise: `accountingservice` logs `severity: fatal` on an
            # unreachable broker and exits, so `restart: always` gives a crashloop. **9 restarts
            # in ~58 seconds**, against a pre-fault RestartCount of 0.
            #
            # There is no dial. Every wrong address - wrong port, wrong host, blackhole IP - ends
            # in the same "run out of available brokers". Kept rather than deleted, like
            # `checkout-currency-misconfig`, because the measurement is the finding: **a consumer
            # in this world does not sit alive and idle when its broker is gone.**
            #
            # See docs/evidence/t7.56-accounting-kafka/.
            params={"env_var": "KAFKA_SERVICE_ADDR", "value": "kafka:9093"},
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
        # --- v2 (T7.0 #5): one definition per new class, each the mechanism its attempt ran ---
        # These are the rehearsal set - the injector-code form of A1, A2, A3, A4b and A8b, with the
        # targets and parameters those attempts measured. T7.1 grows the v2 catalog around them.
        # `world="v2"`: validated against v2's names, refused by the engine on any other world.
        FaultDefinition(
            id="v2-product-catalog-flag-failure",
            fault_class=FaultClass.FEATURE_FLAG,
            target="product-catalog",
            world="v2",
            description=(
                "Flip flagd's productCatalogFailure to on. GetProduct fails for one product, the "
                "catalog's own error ratio stays under the rule and the page lands on frontend "
                "(A1: +6:07). Nothing recorded in change history."
            ),
            params={"flag": "productCatalogFailure", "variant": "on"},
        ),
        FaultDefinition(
            id="v2-cart-flag-failure",
            fault_class=FaultClass.FEATURE_FLAG,
            target="cart",
            world="v2",
            description=(
                "Flip flagd's cartFailure to on. Cart's EmptyCart switches to a store at a host "
                "that does not exist and fails; AddItem and GetCart keep the real store. Checkout "
                "empties the cart after an order is paid and ignores the failure, so orders "
                "complete. A new design (T7.1's feature_flag row 2)."
            ),
            # Read at source (world-v2/src/cart, 2026-09-26): CartService.EmptyCart checks the
            # flag and uses a second ValkeyCartStore built on "badhost:1234", which tries to
            # connect on every call, under a lock, with ConnectRetry 30; checkout's PlaceOrder
            # discards EmptyCart's error (`_ = cs.emptyUserCart`). How long each failing call
            # takes is unmeasured, and is what the rehearsal measures.
            params={"flag": "cartFailure", "variant": "on"},
        ),
        FaultDefinition(
            id="v2-fraud-detection-flag-queue-lag",
            fault_class=FaultClass.FEATURE_FLAG,
            target="fraud-detection",
            world="v2",
            description=(
                "Flip flagd's kafkaQueueProblems to on (value 100). Fraud-detection sleeps a "
                "second before each record it reads, and checkout publishes every order 101 "
                "times, so the consumer falls further behind every second. A new design (T7.1's "
                "feature_flag row 3)."
            ),
            # Read at source (2026-09-26): fraud-detection/main.kt:60 sleeps 1 s per record when
            # the flag is above 0; checkout/main.go:664 re-publishes each order `value` times in
            # goroutines. Accounting reads the same topic without the sleep and gets the
            # duplicates. The earlier mechanism assessment recorded only the consumer side.
            params={"flag": "kafkaQueueProblems", "variant": "on"},
        ),
        FaultDefinition(
            id="v2-ad-flag-failure",
            fault_class=FaultClass.FEATURE_FLAG,
            target="ad",
            world="v2",
            description=(
                "Flip flagd's adFailure to on. The ad service fails one GetAds call in ten with "
                "UNAVAILABLE, after choosing the ads; the frontend's ad requests fail with it. "
                "T7.1's feature_flag row 4, taken by the reserve after row 4 was blocked."
            ),
            # Read at source (ad/src/main/java/oteldemo/AdService.java, 2026-09-26): when the flag
            # is on, `random.nextInt(10) == 0` throws; getAds catches it, sets the span's status to
            # ERROR (no description), adds an `Error` event and logs `GetAds Failed with status`.
            params={"flag": "adFailure", "variant": "on"},
        ),
        FaultDefinition(
            id="v2-payment-flag-unreachable",
            fault_class=FaultClass.FEATURE_FLAG,
            target="checkout",
            world="v2",
            description=(
                "Flip flagd's paymentUnreachable to on. Checkout charges the card through a client "
                "built on badAddress:50051 instead of payment's address, so every order fails at "
                "the charge while payment stays healthy and idle. T7.1's feature_flag row 5 "
                "(holdout)."
            ),
            # Read at source (checkout/main.go chargeCard, 2026-09-26). The target is checkout, not
            # payment: checkout's code reads the flag and swaps the address, and payment is never
            # called. The id is the candidate list's. Each flagged charge builds a new client that
            # is never closed, so checkout's memory is probed at rehearsal.
            params={"flag": "paymentUnreachable", "variant": "on"},
        ),
        FaultDefinition(
            id="v2-email-flag-memory-leak",
            fault_class=FaultClass.FEATURE_FLAG,
            target="email",
            world="v2",
            description=(
                "Set flagd's emailMemoryLeak to 10000x. Email stops clearing the confirmations it "
                "has sent and pads each body to ten thousand times its length, about 19MB kept per "
                "email against a 100M limit. T7.1's feature_flag row 6 (holdout), taken by the "
                "reserve after row 6 was blocked."
            ),
            # Read at source (email/email_server.rb send_email, 2026-09-26): with the multiplier at
            # 1 or more, Mail::TestMailer.deliveries is never cleared and the body is padded by
            # (multiplier - 1) times its length. The variant was chosen before authoring and is not
            # re-tried: measured, one email keeps about 1.9KB times the multiplier.
            params={"flag": "emailMemoryLeak", "variant": "10000x"},
        ),
        FaultDefinition(
            id="v2-product-catalog-freeze",
            fault_class=FaultClass.PROCESS_FREEZE,
            target="product-catalog",
            world="v2",
            description=(
                "docker pause the catalog. Its socket accepts and nothing answers; frontend hangs "
                "to its deadline, seven services behind it go silent, thirteen alerts on ten "
                "services (A2: ServiceNoTraffic on the target +7:36; ~6 min to quiet after the "
                "unpause)."
            ),
        ),
        FaultDefinition(
            id="v2-product-catalog-partition",
            fault_class=FaultClass.NETWORK_PARTITION,
            target="product-catalog",
            world="v2",
            description=(
                "Cut the catalog from the demo network. The same hang-and-cascade as a freeze, "
                "told apart by the target's own once-a-minute export failure in its log "
                "(A3: ServiceNoTraffic +9:36; reconnect restores the compose aliases)."
            ),
            params={"network": "opentelemetry-demo"},
        ),
        FaultDefinition(
            id="v2-cart-store-corruption",
            fault_class=FaultClass.DATASTORE_CORRUPTION,
            target="valkey-cart",
            world="v2",
            description=(
                "Overwrite every cart's hash field with unparseable bytes, swept every 50 ms - "
                "faster than a checkout reads its cart back. checkout pages first at 19%, cart's "
                "own ratio crosses late (A4b: +4:45); the cart's log names the parse failure. "
                "A 5 s sweep pages nothing (A4)."
            ),
            params={"cli": "valkey-cli", "field": "cart", "interval": "0.05"},
        ),
        FaultDefinition(
            id="v2-kafka-disk-fill",
            fault_class=FaultClass.DISK_FILL,
            target="kafka",
            world="v2",
            description=(
                "Fill kafka's log directory - the 256 MiB tmpfs world-v2.override.yml gives it at "
                "the path the broker itself names. The broker halts in two seconds and crashloops; "
                "checkout's produce hangs then fails, both consumers starve (A8b: +6:31 / +7:01 / "
                "+8:31). Restore recreates the broker if the file cannot be reached, then restarts "
                "the consumers, which do not reconnect on their own."
            ),
            params={
                "service": "kafka",
                "directory": "/tmp/kafka-logs",
                "restart_after": "accounting,fraud-detection,checkout",
            },
        ),
        # --- T7.1: the four v1 mechanisms on v2, first candidate of each old row -----------
        # docs/design/t7.1-candidates.md. None of these handlers has run against v2; each is
        # smoked (inject / status / stop / stop) to T1.4's bar before its scenario is authored.
        # Values read off the running world on 2026-09-24, not carried from v1.
        FaultDefinition(
            id="v2-accounting-bad-credential",
            fault_class=FaultClass.BAD_CONFIG,
            target="accounting",
            world="v2",
            description=(
                "Rotate accounting's database password to one Postgres does not accept (T7.0's A6, "
                "the only form 'cert expiry' takes on a world with no TLS). The consumer keeps "
                "consuming and every order fails at the write: ServiceHighErrorRate on accounting "
                "itself (A6 +5:03), its log naming 28P01 password authentication failed."
            ),
            # Live value `Host=postgresql;Username=otelu;Password=otelp;Database=otel` (docker
            # inspect accounting, 2026-09-24): only the password moves. A6's attempt used
            # `WRONG-t70-attempt`, which the change record would hand the agent as the answer; a
            # rotation-shaped value is what a real bad rotation would leave there.
            params={
                "env_var": "DB_CONNECTION_STRING",
                "value": "Host=postgresql;Username=otelu;Password=otelp-2026q3;Database=otel",
            },
        ),
        FaultDefinition(
            id="v2-payment-telemetry-blackout",
            fault_class=FaultClass.BAD_CONFIG,
            target="payment",
            world="v2",
            description=(
                "Repoint payment's OTLP *trace* exporter at a dead address (v1's "
                "payment-telemetry-blackout). The service keeps serving and taking charges; only "
                "its spans stop, so the spanmetrics traffic series drains and ServiceNoTraffic "
                "fires on a service that is working - a config_revert, not a restart."
            ),
            # Live value: payment has only `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
            # (docker inspect, 2026-09-25). The per-signal traces variable overrides it for spans
            # alone, as v1's design did, so payment's metrics - its Node runtime series among them
            # - keep flowing: on v2 the runtime capture is expected to show a live process where
            # the traffic metric shows none. 127.0.0.1:4317 inside the container has nothing
            # listening; the exporter fails fast and the service is not affected.
            params={
                "env_var": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
                "value": "http://127.0.0.1:4317",
            },
        ),
        FaultDefinition(
            id="v2-shipping-quote-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="shipping",
            world="v2",
            description=(
                "Point shipping at a quote host that does not resolve (v1's "
                "shipping-quote-misconfig, v2's variable name). A broken service-to-service "
                "address: on v1 the caller paged and shipping reported no errors of its own."
            ),
            # Live value `QUOTE_ADDR=http://quote:8090` (docker inspect shipping, 2026-09-25);
            # v1's variable was QUOTE_SERVICE_ADDR and its host quoteservice. Only the host moves.
            # The cart row's lesson is checked at rehearsal: a dependency address read at startup
            # can make a v2 service exit rather than fail per call. Shipping calls quote over HTTP
            # per request, so a host that does not resolve should fail each quote, not the start.
            params={"env_var": "QUOTE_ADDR", "value": "http://quote-gone:8090"},
        ),
        FaultDefinition(
            id="v2-frontend-cart-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="frontend",
            world="v2",
            description=(
                "Point the frontend at a port on the cart host where nothing listens. Cart stays "
                "healthy and keeps serving checkout; the storefront's own cart calls fail. A new "
                "design (T7.1's second bad_config reserve)."
            ),
            # Live value `CART_ADDR=cart:7070` (docker inspect frontend, 2026-09-26). Only the port
            # moves: the host resolves and refuses, where shipping's quote-gone did not resolve, so
            # the two scenarios' error text differs. The frontend builds its cart gRPC client
            # lazily and reads CART_ADDR by destructuring process.env at runtime
            # (gateways/rpc/Cart.gateway.ts), which Next's build-time `env` inlining does not
            # replace - so the change should take effect on a recreate, and a startup exit (the
            # cart row's lesson) is not expected. Both are checked at rehearsal.
            params={"env_var": "CART_ADDR", "value": "cart:7071"},
        ),
        FaultDefinition(
            id="v2-accounting-kafka-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="accounting",
            world="v2",
            description=(
                "Point accounting's Kafka bootstrap address at a port on the Kafka host where "
                "nothing listens. A consumer cut from its broker: nobody calls accounting, so it "
                "cannot error or slow down; it can only go quiet while the broker, and the other "
                "consumer of the same topic, carry on. A new design (T7.1's holdout row 5)."
            ),
            # Live value `KAFKA_ADDR=kafka:9092` (docker inspect accounting, 2026-09-26). Not the
            # candidate list's `kafka:9093`: that was v1's value, where nothing listened on 9093,
            # and on v2 9093 is Kafka's KRaft controller listener (nc -z: open). 9094 is closed
            # (nc -z: exit 1), so the connection is refused, which is the row's mechanism
            # (decided 2026-09-26, written in the candidate list). v1's accounting logged fatal and
            # crashlooped on an unreachable broker (T7.56); v2's is .NET, subscribes without
            # connecting and blocks in Consume() while the client retries, so it should stay up.
            # Checked at rehearsal: a crashloop is bad_deploy's page and would block it.
            params={"env_var": "KAFKA_ADDR", "value": "kafka:9094"},
        ),
        FaultDefinition(
            id="v2-checkout-currency-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="checkout",
            world="v2",
            description=(
                "Point checkout at a currency host that does not exist. The orchestrator itself is "
                "misconfigured: every order fails at its first price conversion, before shipping "
                "is asked for a quote, while currency stays healthy and goes idle. A new design "
                "(v1's spare, never recorded; T7.1's holdout row 6)."
            ),
            # Live value `CURRENCY_ADDR=currency:7001` (docker inspect checkout, 2026-09-26). The
            # host becomes `currencyservice`, v1's name for the service: a stale value of the
            # kind a config carried across a rename leaves, which does not name the answer, and
            # which does not resolve on v2 (getent from the kafka container: no answer; `currency`
            # resolves). Checkout builds the client with grpc.NewClient, which does not connect at
            # startup, so each Convert should fail rather than the container exit. Checked at
            # rehearsal: a crashloop is bad_deploy's page and would block it.
            params={"env_var": "CURRENCY_ADDR", "value": "currencyservice:7001"},
        ),
        FaultDefinition(
            id="v2-cart-valkey-misconfig",
            fault_class=FaultClass.BAD_CONFIG,
            target="cart",
            world="v2",
            description=(
                "Point cart at the wrong valkey port (v1's cart-redis-misconfig, renamed with the "
                "store). The store is up and the config is wrong: every cart operation fails, a "
                "config_revert, not a rollback."
            ),
            # Live value `valkey-cart:6379` (docker exec cart printenv, 2026-09-24).
            params={"env_var": "VALKEY_ADDR", "value": "valkey-cart:6380"},
        ),
        FaultDefinition(
            id="v2-cart-bad-image-tag",
            fault_class=FaultClass.BAD_DEPLOY,
            target="cart",
            world="v2",
            description=(
                "Deploy cart on an image tag that was never pushed (v1's cart-bad-image-tag). The "
                "container never starts, so cart goes dark rather than erroring."
            ),
            # The running image is ghcr.io/open-telemetry/demo:2.2.0-cart (docker inspect); a
            # plausible hotfix tag on the real repository, so the investigator has to notice the
            # tag is wrong rather than that the image is foreign.
            params={
                "image": "ghcr.io/open-telemetry/demo:2.2.0-cart-hotfix.2",
                "expect_start": "no",
            },
        ),
        FaultDefinition(
            id="v2-shipping-wrong-image",
            fault_class=FaultClass.BAD_DEPLOY,
            target="shipping",
            world="v2",
            description=(
                "Deploy the ad service's image into shipping's slot (v1's shipping-wrong-image). "
                "The image resolves and the deploy succeeds, but a JVM does not fit a container "
                "sized for a Rust binary, so it is killed at start, over and over."
            ),
            # Read and measured 2026-09-27: v2's shipping is Rust with a 20M limit (5.7MiB used at
            # rest); the ad image is a Temurin 21 JRE with the OTel Java agent on
            # JAVA_TOOL_OPTIONS, and it also refuses to start without AD_PORT, which shipping's
            # environment does not set. Either way it cannot serve; v1's restart loop is the
            # expectation, measured at rehearsal.
            params={
                "image": "ghcr.io/open-telemetry/demo:2.2.0-ad",
                "expect_start": "yes",
            },
        ),
        FaultDefinition(
            id="v2-ad-bad-image-tag",
            fault_class=FaultClass.BAD_DEPLOY,
            target="ad",
            world="v2",
            description=(
                "Deploy ad on an image tag that was never pushed. The container never starts, so "
                "ad goes dark: the storefront's ad requests fail while orders are untouched. "
                "T7.1's bad_deploy row 3, taken by a new reserve after row 3 and the listed "
                "reserve were passed over."
            ),
            # Checked 2026-09-27: the tag does not resolve in the registry and is not on the host;
            # the running image is 2.2.0-ad. A plausible hotfix tag on the real repository, as
            # v2-cart-bad-image-tag's, so the investigator has to notice the tag is wrong.
            params={
                "image": "ghcr.io/open-telemetry/demo:2.2.0-ad-hotfix.2",
                "expect_start": "no",
            },
        ),
        FaultDefinition(
            id="v2-email-wrong-image",
            fault_class=FaultClass.BAD_DEPLOY,
            target="email",
            world="v2",
            description=(
                "Deploy the quote service's image into email's slot (v1's email-wrong-image). "
                "The image resolves and the deploy succeeds, but the quote service's PHP server "
                "binds to QUOTE_PORT, which email's environment does not set, so it dies with a "
                "fatal error as it starts and restarts, over and over, and never serves."
            ),
            # Probed 2026-09-27 in a throwaway container with email's environment: the image
            # exists in the registry and on the host; `php public/index.php` threw
            # `InvalidArgumentException: Invalid URI "tcp://0.0.0.0:"` and exited 255 in 190 ms,
            # not killed for memory. v1's shape - the log names the cause outright - and the
            # opposite of v2-shipping-wrong-image's, whose JVM is killed at 137 in a slot too
            # small for it. Here the slot (100M) is ample; the program is wrong for its
            # environment.
            params={
                "image": "ghcr.io/open-telemetry/demo:2.2.0-quote",
                "expect_start": "yes",
            },
        ),
        FaultDefinition(
            id="v2-ad-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="ad",
            world="v2",
            description=(
                "Shrink ad's memory limit below its JVM working set (v1's ad-memory-squeeze). The "
                "heap was sized for the old ceiling, so the kernel OOM-kills it and the frontend "
                "loses its ad panel while everything else serves."
            ),
            # Resting 238.8MiB of a 300MiB limit (docker stats, 2026-09-24); 192m, 80 % of that,
            # was the starting value for the smoke, with the rehearsal to measure it. Measured
            # 2026-09-27 before authoring, from ad's own JVM series: it sizes its heap from the
            # container limit (a 121.8 MiB ceiling against 300M, about 40 %), so a JVM restarted
            # under 192m would take a 78 MiB heap and could settle in - one kill and a quiet
            # recovery, the edge of T7.20's band that cart-memory-squeeze fell off. What it cannot
            # shrink: 91.6 MiB of non-heap and about 80 MiB the container holds outside the JVM
            # altogether (230 MiB in docker stats against 149 committed). The rule, applied once:
            # the JVM's own committed memory at its eight-hour high (157.6 MiB), rounded down to
            # 16 MiB - 62 % of the working set, so the running JVM is killed at once, and nothing
            # left for the process's own 80 MiB, so a restarted one cannot reach a serving state.
            params={"memory": "144m"},
        ),
        FaultDefinition(
            id="v2-fraud-detection-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="fraud-detection",
            world="v2",
            description=(
                "Shrink fraud-detection's memory limit below what its JVM needs to run (v1's "
                "frauddetection-memory-squeeze). It consumes from Kafka and nothing calls it, so "
                "it dies without the storefront noticing - the smallest page there is."
            ),
            # Measured 2026-09-27 before authoring, from its own JVM series, under the 500M limit
            # the world revision gave it: 256 MiB in docker stats; heap ceiling 121.8 MiB (the
            # same figure as ad's against 300M - the JVM's own setting, not a share of the limit),
            # heap used 51, non-heap 100, committed 168.1 at its eight-hour high; about 88 MiB
            # held outside the JVM. The row's rule, applied once: the JVM's committed memory at
            # its eight-hour high rounded down to 16 MiB - 62 % of the working set, so the running
            # JVM dies at once, and under the ~190 MiB a restarted one needs before it can serve.
            params={"memory": "160m"},
        ),
        FaultDefinition(
            id="v2-cart-memory-squeeze",
            fault_class=FaultClass.RESOURCE_EXHAUSTION,
            target="cart",
            world="v2",
            description=(
                "Shrink cart's memory limit below what its .NET runtime needs to run - a v1 "
                "definition T7.20 probed at 200m (killed, back before detection) and 32m (never "
                "ran long enough to export) and never authored. The storefront and every order "
                "lose the cart; the same absence as a bad cart deploy, with a limit in the record "
                "and a process that keeps starting in the log."
            ),
            # Measured 2026-09-27 before authoring, from cart's own .NET series: 94.8 MiB working
            # set (83.4 to 111.9 over eight hours) in a 160M container, of which the GC has
            # committed only 23.6 (24.9 at its high) - almost all of what cart holds is the
            # runtime outside its managed heap. The row's rule restated for .NET, applied once:
            # the working set's eight-hour low less the GC's committed high (58.5 MiB), rounded
            # down to 16 MiB. Half the running working set, so the process dies at once, and under
            # the ~60 MiB a restarted one needs outside its heap, so it cannot settle in.
            params={"memory": "48m"},
        ),
        FaultDefinition(
            id="v2-cart-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="cart",
            world="v2",
            description=(
                "Add 300ms of network delay to cart (v1's cart-dependency-latency), past the "
                "250ms p95 threshold, so checkout slows without anything erroring outright."
            ),
            # cart is on opentelemetry-demo with one interface (docker inspect, 2026-09-24).
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="v2-valkey-cart-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="valkey-cart",
            world="v2",
            description=(
                "Add 300ms of network delay to cart's store, not to cart (v1's "
                "redis-cart-dependency-latency). Cart's handler waits on replies that are late, "
                "so cart looks slow while the thing that is slow has no spans, no metrics and no "
                "name anywhere in the traced graph."
            ),
            # The target is the datastore, and that is the whole point. Checked 2026-09-27:
            # valkey-cart has an eth0, a Loki stream of its own (its five-minute save, five lines
            # each) and not one Prometheus series under any label. A container target, as
            # v2-cart-dependency-latency is; pumba runs tc from its sidecar image into the
            # target's network namespace, so the store stays the image the world pins.
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="v2-payment-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="payment",
            world="v2",
            description=(
                "Add 300ms of network delay to payment, a leaf that only checkout calls. Its "
                "delayed replies land after its own server spans have closed, so payment never "
                "looks slow; checkout does, on the charge, and nothing else moves. T7.1's "
                "dependency_latency row 3, a new design."
            ),
            # Measured 2026-09-27 before authoring: payment makes no call per charge (its only
            # client spans are its flag stream and a DNS lookup, at 0.000/s), so v1's
            # ad-dependency-latency lesson applies - the leaf's p95 will not move. The observer
            # is checkout: Charge and the PlaceOrder that contains it are 15.8% of its
            # non-internal spans, both landing in the latency histogram's 200-400ms bucket under
            # the delay, which interpolates to a p95 near 335ms. The frontend's checkout spans
            # are 4.4% of its total, under the 5% a p95 needs. Not tuned: the row's 300ms.
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
        FaultDefinition(
            id="v2-product-catalog-dependency-latency",
            fault_class=FaultClass.DEPENDENCY_LATENCY,
            target="product-catalog",
            world="v2",
            description=(
                "Add 300ms of network delay to the product catalog (v1's "
                "productcatalog-dependency-latency). It sits on the product listing, the "
                "recommendations and the checkout path, so the slowdown shows up everywhere at "
                "once and the shared dependency is the thing to find."
            ),
            # Measured 2026-09-27 before authoring: the catalog makes one sql.conn.query round
            # trip per lookup, so the delay sits inside its own spans (unlike payment's), and its
            # callers carry it at 23.3% (frontend), 14.8% (checkout) and 49.8% (recommendation)
            # of their non-internal spans. Interface read with ip link from a helper in its
            # network namespace (the image has no shell).
            params={"delay_ms": 300, "jitter_ms": 0, "duration": "1h", "interface": "eth0"},
        ),
    )
)


def by_id(fault_id: str) -> FaultDefinition | None:
    return next((f for f in CATALOG if f.id == fault_id), None)
