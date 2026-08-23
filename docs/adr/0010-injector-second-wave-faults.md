# ADR-0010: A second wave of faults - CPU quota, unresolvable image tags, and flag-driven failure

- **Status:** accepted
- **Date:** 2026-08-22
- **Task:** T1.5 (scenario coverage) - extends ADR-0007

## Context
ADR-0007 gave the injector one mechanism per fault class and four definitions - one per
class, each against a different service. That is enough to prove the injector works and
nowhere near enough to score an agent on. Four scenarios sharing four targets means an
agent can do well by memorising "recommendation means memory, cart means latency" without
ever reading the evidence.

Widening coverage means two different things, and they carry different risk:

- **New targets on proven mechanisms** are nearly free. The mechanism is already verified
  against the live world; only the numbers and the blast radius are new.
- **New mechanisms** are not. Each one needs its own answer to ADR-0007's three
  requirements - reversible, deterministic, applied from outside the pinned world.

This ADR covers three new mechanisms and the definitions built on them. No new fault
*classes*: `FaultClass` is the contract the eval harness and the scenario schema validate
against, and T7.0 owns extending it.

## Decision

### A fault class may own more than one mechanism

`resource_exhaustion` now squeezes memory *or* CPU; `bad_deploy` now ships a bad build *or*
a tag that resolves nowhere. The class is what a scenario is scored against - it answers
"what kind of failure was this?" - and both CPU starvation and memory starvation answer
that question the same way. Splitting them into separate classes would make the answer key
depend on an injector implementation detail.

Which mechanism runs is decided by the definition's params, not by a flag:

| Class | Params | Mechanism |
|---|---|---|
| `resource_exhaustion` | `memory` | `docker update --memory` on a container |
| `resource_exhaustion` | `cpus` | compose override on `deploy.resources.limits.cpus` |
| `bad_deploy` | `image` + `server` | build the image from the stub context, then swap to it |
| `bad_deploy` | `image` alone | swap to the tag as written - and it resolves nowhere |

`bad_deploy` now ships three distinct failure *shapes* off those two mechanisms, which is
the point of having three: a build that serves and fails every call
(`flag-service-bad-deploy`), a build that serves correctly and then exits over and over
(`flag-service-crashloop`), and a tag that never starts anything at all
(`cart-bad-image-tag`). An agent that has learned "bad deploy means steady 5xx" should get
two of the three wrong.

A definition carrying both `memory` and `cpus` is refused: two resources squeezed at once
is two incidents wearing one label, and the scenario would have no single right answer.
`server` and "the tag does not exist" are mutually exclusive by construction - you cannot
both build an image and claim it is missing - so that pair needs no guard.

### CPU quota goes through compose, not `docker update`

`docker update --cpus` would have mirrored the memory path exactly and applied live. It was
rejected: the world declares its resource limits in `deploy.resources.limits`, and a quota
set behind compose's back is invisible to anyone reading the compose files during the
incident. Going through a generated override keeps every declared limit in one place and
makes the change inspectable the same way the config faults are.

The cost is a container recreate, because compose only reads `deploy.resources.limits.cpus`
at create time. Currency comes back within seconds - far inside `ServiceNoTraffic`'s
three-minute window - but the incident does begin with a restart, which an investigator
may see. That is realistic for a resource-limit change and was judged not worth avoiding.

The pre-fault quota is inspected before the override goes on and written into the restore
record. Dropping the override is what actually restores the quota - the world's own compose
files are the original - but `status` and the incident transcript have to be able to state
what the world is being returned to without re-reading a file that may have been edited
under us since. The fault targets a compose *service*; the container behind it has a
different name in this world, so the injector asks `docker compose ps --quiet` which one it
is rather than guessing at the naming convention. A service that is not running is refused:
there is no quota to capture, and ADR-0007's rule is that restore never guesses.

### An unresolvable tag has to take the old container down first

Compose resolves every image before it touches any container. Point a service at a tag that
does not exist and `up` fails with the healthy container still running - the deploy breaks
and the world does not, which is no fault at all. So this mechanism stops the service
first, then applies the override and *tolerates* the failing recreate, because that failure
is the fault rather than an error to roll back from. An explicitly stopped container is not
resurrected by its `restart: always` policy, so the service stays dark.

Stopping first is also what a real rolling deploy does, and it makes the outage independent
of how a given compose version happens to order pull and create - ADR-0007's determinism
requirement. The override file survives the failed recreate on purpose: it is the evidence
of *why* the service is down, and the thing `stop` has to remove.

Everywhere else, a failed recreate still rolls itself back. A fault that fails to inject
returns no restore record, so nothing would ever clean up an override it left behind. The
same rollback runs in the opposite case here - the tag resolving when it was supposed not
to - because that is equally a fault that did not fire.

### The flag stub gets a switch, so the demo's own failure modes become injectable

`FAULTLINE_ENABLED_FLAGS` is a comma-separated list of flag names the stub answers
"enabled" to; empty by default, so an unconfigured stub behaves exactly as ADR-0006
specified - every flag off. Set it through the existing `bad_config` mechanism and the
demo's own instrumented failures become available without a rebuilt image.

`productCatalogFailure` is the first: `world/src/productcatalogservice/main.go` reads it on
every `GetProduct` and returns `Internal` for one product id when it is on. That gives a
*partial* failure - a fraction of one service's traffic, not all of it - which no other
fault in the catalog produces, and it is failure code the demo authors wrote rather than
anything Faultline injected into the request path.

### A crash loop needs the container to stay up longer than 10 seconds

`server_crash.py` serves correctly and then calls `os._exit(1)` on a timer - `sys.exit`
would unwind the timer thread alone and leave the gRPC server serving. The world gives the
flag service `restart: always`, so the container comes back and does it again.

The delay is 20s, and `FAULTLINE_CRASH_AFTER_SECONDS` must stay above 10. Docker resets a
container's restart backoff only once it has stayed up for ten seconds; crash faster than
that and the backoff doubles away toward a minute between attempts, at which point the
fault stops looking like a crash loop and starts looking like `cart-bad-image-tag`. Two
faults with the same signature is one fault and one piece of dead weight in the catalog.

### Eight new definitions

| ID | Class | Target | What it should trip |
|---|---|---|---|
| `currency-cpu-throttle` | resource_exhaustion | `currencyservice` (service) | `ServiceHighLatency` |
| `flag-service-crashloop` | bad_deploy | `featureflagservice` (service) | callers' error rate, in bursts |
| `ad-memory-squeeze` | resource_exhaustion | `ad-service` (container) | OOM kill, restart loop |
| `cart-bad-image-tag` | bad_deploy | `cartservice` (service) | `ServiceNoTraffic` |
| `productcatalog-dependency-latency` | dependency_latency | `product-catalog-service` (container) | `ServiceHighLatency` |
| `checkout-currency-misconfig` | bad_config | `checkoutservice` (service) | `ServiceHighErrorRate` |
| `product-catalog-flag-failure` | bad_config | `featureflagservice` (service) | `ServiceHighErrorRate`, partial |

Note the two naming worlds again, as ADR-0007 warned: faults reaching containers directly
(`docker update`, `tc netem`) name the container; faults going through compose name the
service. They are not interchangeable.

## Consequences

**The numbers in these definitions are not yet measured.** ADR-0007's defaults were tuned
against the live world - 48m because 64m never fired, 300ms because the alert sits at
250ms. These are reasoned, not rehearsed:

- `currency-cpu-throttle` at `0.05` CPU is 5ms of runtime per 100ms CFS period. Currency's
  per-call work is short, so a quota above its average demand would never throttle and one
  far below it would queue until callers time out - turning a latency incident into an
  error-rate one. 0.05 is aimed just under demand, so the container exhausts its slice in
  most periods and stalls to the next. If p95 stays under 250ms, halve it; if
  `ServiceHighErrorRate` fires instead, raise it.
- `ad-memory-squeeze` at `256m` against the 700M ceiling `world-arm64.override.yml` grants.
  That ceiling was itself raised from the demo's native-x86 300M because the JVM sits at
  its limit under emulation, so the working set is known to be north of 300M. `docker
  update` moves the cgroup limit under a JVM that already sized its heap for 700M, which is
  what should make the kill prompt rather than eventual.

- `flag-service-crashloop` at 20s is a guess at "long enough to serve real traffic between
  crashes, short enough that the sawtooth is visible inside an alert window". Whether it
  trips anything at all is the open question: the flag service's own traffic may be too
  thin for `ServiceNoTraffic`, and the callers' error bursts may average out below the 5%
  the error-rate rule wants. It may turn out to be a fault whose only signal is the restart
  count - which is a legitimate scenario, but a different one from the description.

Until each has been injected, observed and reverted against the live world, no scenario
built on them may be marked `rehearsed: true`.

**`product-catalog-flag-failure` needs a rebuilt stub image.** The env var only exists in
`faultline/ffs-stub:1` once `make ffs-stub` has been re-run; compose runs `--no-build`, so
an old image will ignore the override and the fault will silently do nothing. Rebuild the
stub and recreate `featureflagservice` before rehearsing it. A stale image is the one
failure mode here that looks like a working injection.

**`cart-bad-image-tag` depends on the tag staying unresolvable.**
`ghcr.io/open-telemetry/demo:v1.2.1-cartservice-hotfix.2` is chosen to look like a plausible
hotfix against the world's real image name. If upstream ever publishes it, the recreate
succeeds and no fault is injected. That case is refused loudly rather than reported as a
success - the injector rolls the override back off and tells the operator to pick another
tag - because a fault that silently did not fire produces a scenario scored against a world
with nothing wrong with it, which is the worst outcome available here.

**Restoring an unresolvable-tag deploy has to pull.** Every other compose restore recreates
from an image already on the host. This one comes back on the world's real image, which is
present - but a pruned host would turn `stop` into a pull, and a pull into a network
dependency in the reset path.

Revisit if: a scenario needs two faults on one target at once (still unmeasured, per
ADR-0007), or T7.0's new classes want the params-select-the-mechanism pattern generalised
into something declarative.
