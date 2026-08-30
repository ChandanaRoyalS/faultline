# S6 rescored under the current scorer

**Why this exists.** T7.10 found that S5's stored figures had been computed by a pre-T7.3 scorer,
so comparing them to S6 would have credited the world with a scorer fix. The same thing happened
again between S6 and S7, and this is the check.

## The confound

`src/evalharness/scoring.py` last changed at **T7.17, 2026-08-29 00:38:00 -0500**.

| S6 run | timestamp |
|---|---|
| earliest | `20260828T072535Z` |
| latest | `20260828T154652Z` |

**Every S6 run predates the scorer change.** The change before that was T7.5 (2026-08-28 01:26),
which predates every S6 run, so **T7.17 is the only scorer movement in the window** and the rescore
is narrow by construction: it can only touch fix-class labels, and only where a scenario carries
`also_correct_remediation`.

## What T7.17 changed

`LabelScore.also_correct` — ADR-0022 §1.2 decides a fix class by which remediation actually works
and assumes exactly one does. ADR-0027 measured two working fixes for `dependency_latency`, so
`cart-dependency-latency` carries `also_correct_remediation: [config_revert]` and both count.

## Result

| scenario | fault | fix stored | fix rescored | by alternative | triage R / P | cost |
|---|---|---|---|---|---|---|
| `ad-memory-squeeze` | `resource_exhaustion` ✔ | ✔ | ✔ | | 1.00 / 0.43 | $0.5680 |
| `cart-bad-image-tag` | `bad_deploy` ✔ | ✔ | ✔ | | 0.80 / 0.67 | $0.5377 |
| `cart-dependency-latency` | `dependency_latency` ✔ | ✘ | **✔** | **yes** | 1.00 / 0.33 | $0.5705 |
| `cart-redis-misconfig` | `bad_config` ✔ | ✔ | ✔ | | 0.80 / 0.67 | $0.6189 |
| `product-catalog-flag-failure` | `bad_config` ✔ | ✔ | ✔ | | 1.00 / 0.43 | $0.4978 |
| `shipping-wrong-image` | `unknown` ABST | ✘ | ✘ | | 0.75 / 0.60 | $0.5721 |

| | stored | **rescored** |
|---|---|---|
| scenarios scored | 6 | 6 |
| coverage | 5 / 6 | 5 / 6 |
| fault class, of answered | 5 / 5 | 5 / 5 |
| **class of fix, of answered** | **4 / 5** | **5 / 5** |
| judge `same_mechanism` | 5 / 6 | 5 / 6 |

**Exactly one label moved**, and it is the one the pre-registration named in advance.
`cart-dependency-latency` returned `config_revert` against a labelled truth of `restart`; both are
measured to work, so it is **correct by alternative** and is reported that way rather than folded
into the headline.

**Triage is untouched** — every recall/precision pair reproduces S6's published figures to two
decimals, which is the check that T7.17 did not reach triage. Total cost reproduces at **$3.3650**.

## What is compared in the sweep

The **rescored** S6 column. The raw stored figure of 4/5 is not compared to anything, because
comparing it to S7 would attribute T7.17's fix to the world — the exact error T7.10 caught.
