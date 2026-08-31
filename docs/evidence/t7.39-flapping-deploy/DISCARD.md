# D3 `payment-flapping-deploy` — disqualified at the desk, zero world time

**Four of the seven criteria failed, and the world was never touched.** No injection, no probe, no
recording, no money. This is the cheapest discard the project has produced.

## Check 1 — the injector's third shape does not exist

T7.34's audit said the injector "documents three shapes — never starts, starts then fails every
call, flaps", and D3 was designed to fill the third. **It documents two.**

> `BadDeployFault`: *"Ship a bad release: one that starts and fails on the hot path, or one that
> never starts. **Both are the same image swap.**"*

The implementation has exactly two paths, selected by a required `expect_start` param:
`"no"` → the tag resolves nowhere and nothing starts; `"yes"` → the image resolves, the container
starts, and what it does next is the fault. **There is no flap path.**

**"Flaps" traces to this project's own prose, not to the injector.** It appears in SPLIT.md §"What
determines a class's slot count" (T7.21) and in CATALOG.md (T7.34) — both written by this project —
and nowhere in `src/injector/`. **T7.34's audit asserted a property of the injector by reading a
document that had asserted it first.** That is the error the audit was supposed to catch, committed
by the audit.

**The one scenario that ever attempted the shape is blocked.** `flag-service-crashloop` carries an
`INVALID.md`: *"NO ALERT FIRED — AND NONE COULD HAVE."* **That reason does not transfer** —
featureflagservice emits no `calls_total` at all, so its rules could never evaluate, and
`paymentservice` is on that same file's list of fifteen services that do have it. The precedent is
not what kills D3; it is only what should have prompted reading the injector first.

## Check 3 — the page would near-duplicate an existing one

Both recorded `bad_deploy` pages, read before any probe:

| | `cart-bad-image-tag` (`expect_start: no`) | `shipping-wrong-image` (`expect_start: yes`) |
|---|---|---|
| onset | 286s | 198s |
| at fire | `ServiceHighErrorRate` × 3 | **`ServiceHighErrorRate/checkoutservice`** |
| shape | 3 error + 2 latency + **7 `ServiceNoTraffic`** | 3 error + **5 `ServiceNoTraffic`**, target included |

A flapping `paymentservice` produces caller errors at `checkoutservice` while it is down and a
`ServiceNoTraffic` cascade through the order path — **`ServiceHighErrorRate/checkoutservice` at
fire plus `ServiceNoTraffic` on the target and the downstream consumers.** That is
`shipping-wrong-image`'s page.

## Check 4 — the confusability is not in the recorded evidence, and this is the disqualifying one

D3 exists to be confusable with an OOM. Separating them needs the container's exit reason, or a
restart count, or memory behaviour. **None of the three is in a bundle.**

**Container state is not captured.** A bundle holds `metrics/` (five Prometheus captures),
`logs/`, `manifest.json`, `queries.md`, `incident.md`. There is no container inspect and no restart
count — and `cart-bad-image-tag`'s own narrative says so in as many words:

> *"That the pull failed and no container was ever created is an **inference from the change**"* …
> *"container was created and died instantly or never created at all **is not visible from here**"*

**That is precisely D3's distinguishing signature, and the catalog already records it as invisible.**

**Memory evidence is absent for this target specifically, and the asymmetry is the point:**

| bundle | runtime series |
|---|---:|
| `ad-memory-squeeze` — the OOM this must be told apart from | **48** |
| `paymentservice` — measured live | **0** |

An OOM on `adservice` carries 48 series of JVM memory evidence. A flap on `paymentservice` would
carry none — **so a responder could neither rule OOM in nor rule it out from the bundle.** The
distinction collapses to `change_history` alone: an image change versus a memory-limit change.

**T7.38 produced an item separated by exactly one tool class one task ago**, and labelled it narrow.
A second consecutive one — where the single class is also the *only* thing making the item's whole
premise answerable — is not narrow. **It is unanswerable, which the criteria named as disqualifying
rather than hard.**

## What would make a flapping deploy viable, stated so it is not re-proposed blind

**A target that exports runtime families**, so flat memory under a flap contrasts against climbing
memory under an OOM and the item becomes answerable from the bundle. The JVM services qualify —
`adservice` carries 48 series.

**The obstacle is that those are already the `resource_exhaustion` targets**, which raises
cross-split service overlap (`test_cross_split_service_overlap_is_the_recorded_set`) and would put
the same service behind two classes. That is a real design question and not a detail.

**It also needs a mechanism.** `BadDeployFault` swaps an image; a flap needs an image whose
entrypoint exits under `restart: always`. All seventeen demo images present locally are servers.
**Producing one is new injector work**, which is outside what "build D3" was scoped as.

**Retargeting was deliberately not done here.** Switching target to make a candidate pass is how
three candidates were disqualified in this project after passing a gate on paper, and the criteria
forbade it in advance.

## What this leaves

**`bad_deploy` dev stays at 2, below SPLIT.md's floor of 3.** `bad_deploy-4` is unfilled and has no
candidate; T7.35 already recorded `bad_deploy-5` as deliberately empty. The class holds **2 of 4
allocated dev slots**, and the floor argument — *"two cannot show a spread"* — now applies to it as
it does to `dependency_latency`.

**Disqualified candidates now number six of seventeen proposed (35%)**, up from T7.34's measured 31%.
