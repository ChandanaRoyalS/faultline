# ADR-0027: `dependency_latency` has two working fixes, and the scorer must accept both

- **Status:** accepted
- **Date:** 2026-08-29
- **Task:** T7.17 (which fix actually works)
- **Amends:** ADR-0022 §1.2 (the fix test), ADR-0008's withdrawal of `restart`'s provisional marking
- **Evidence:** `docs/evidence/t7.17-fix-class/`

## Context

`CLASS_DISPUTES` has carried two entries on `cart-dependency-latency` since T4.3. Ground truth says
`restart`; the agent answered `config_revert` under three stamps. ADR-0022 §1.2 decides the class by
**which remediation actually works** — and the register recorded an answer, *"pumba binds to the
container present, so a restart durably clears the delay while there is no configuration to
revert"*, measured on 2026-08-23 against a world since re-recorded. ADR-0008 withdrew `restart`'s
"provisional / least-bad fit" marking on that measurement without re-testing.

Nobody had tested the other half.

## The measurement

Eight attempts, pre-registered before any injection, reading the qdisc directly rather than
inferring from a percentile that lags two minutes behind the world.

| candidate | operation | durably cleared |
|---|---|---|
| **R** `restart` | `docker restart cart-service` | **3 / 3** |
| **T** `config_revert` | `tc qdisc del dev eth0 root`, container and sidecar untouched | **3 / 3** |
| S control | stop the pumba sidecar | 2 / 2 |

The fault took every time (`netem … delay 300.0ms`, p95 642–671ms). "Durably cleared" means no
netem at +60s **and** +120s.

**`config_revert` is not a name for something that does not exist here.** Deleting the netem qdisc
from cartservice's `eth0` clears the delay with the container never restarted and the pumba sidecar
still `Up` — pumba applies its rule once and waits out `--duration` rather than reconciling, so
nothing reapplies it. p95 returns to 1.9ms, the committed baseline, 3/3.

It is also the *less disruptive* fix: T returns p95 to exactly 1.9ms where R leaves 3.8–4.8ms at
the same point, the post-restart warming CATALOG.md already documents.

## Decision

**The label is right and the agent was also right.** `restart` stays as
`expected_remediation_class` — it works, and it is what the bundles were recorded against.
`config_revert` is recorded as a second **measured** working fix, and the scorer counts it correct.

**This is not "the agent was wrong and we are being generous."** ADR-0022 §1.2 says the class is
decided by which remediation works. Two do. The rule as written assumes one, and where two work it
does not select between them — so scoring the agent against whichever the author wrote down first
is grading on taste, not on the rule.

### What the scorer does with a fault that has two working fixes

`Scenario.also_correct_remediation`, a list of remediation classes **measured** to fix the fault
durably. `LabelScore.correct` accepts the labelled class or any member. `correct_by_alternative`
stays on the record so a reader can see the answer was right by the second route rather than the
first, and the applied set is written into the scored output rather than left to be inferred from
the catalog as it stands later.

Three deliberate limits:

- **The bar is measurement, not plausibility.** An entry means the remediation was applied to a
  live injection and the fault verifiably cleared and stayed cleared. Nothing goes in because it
  sounds reasonable.
- **It is not in `scenario_fingerprint`.** `expected_remediation_class` is, and it is unchanged —
  verified, `c982653939a5c1ff` before and after — so **no bundle is invalidated**. A bundle records
  what the fault did to the world; it is not made wrong by a later discovery about how to undo it.
- **It is a scoring policy, read at scoring time**, because no recorded bundle carries it and none
  is re-recorded to gain one.

### The register keeps both entries, one resolved and one corrected

**The fix-class entry is resolved for the agent.** Kept rather than deleted: it is the record of a
disagreement settled wrongly for three stamps, and deleting it would hide that.

**The fault-class entry keeps its conclusion and loses its reasoning.** It too was resolved by the
fix test — a test both readings now pass, so it discriminates nothing and cannot carry the entry.
`dependency_latency` still stands, on different grounds: `bad_config` in this catalog means a
configuration value was *set wrong*, and nothing on cartservice was. Shaping was added alongside
it, and the service then behaved as a slow dependency. Corrected rather than quietly left, because
leaving a falsified premise under a conclusion one happens to agree with is how a register stops
being evidence.

## What it does to the tables

Every fix-class cell that counted `config_revert` on a `dependency_latency` scenario as a miss
gains one in its numerator; denominators are unchanged, because those runs answered. Corrected in
place with **originals struck and visible**, per T7.3's precedent:

| where | was | now |
|---|---|---|
| `RESULTS.md` — S6, the current-world headline | class of fix **4/5** | **5/5** |
| `SWEEP-2026-08-26.md` | class of fix **6/7** | **7/7** |
| `SWEEP-2026-08-26-taxonomy.md` — `dependency_latency` row | S1 fix **0/1**, S2 fix **0/1** | **1/1**, **1/1** |
| `SWEEP-2026-08-26-taxonomy.md` — totals | **6/7**, **3/4** | **7/7**, **4/4** |
| `SWEEP-2026-08-27-evidence.md` — S3, S4 | **5/6**, **3/4** | **6/6**, **4/4** |
| `SWEEP-2026-08-27-locus.md` — S3, S4, S5 | **5/6**, **3/4**, **6/7** | **6/6**, **4/4**, **7/7** |
| `HOLDOUT-2026-08-27-entry3.md` — entries 1 and 3 | **0/1**, **2/3** | **1/1**, **3/3** |

**The holdout moves too**, and that is the one worth saying out loud: `productcatalog-dependency-latency`
returned `config_revert` on the same mechanism, so the held-out fix-class figure goes from 2/3 to
3/3. A correction that improves a headline deserves more scepticism than one that worsens it —
which is why it rests on eight recorded attempts and a protocol registered before the first
injection, and why the originals are left struck rather than overwritten.

## Consequences

- **No fault class changes.** Only the class of fix, and only for the two `dependency_latency`
  scenarios.
- `productcatalog-dependency-latency` carries the same field on the same mechanism, untested
  directly. Stated as inference, not measurement: it is the identical pumba/netem injection, and
  the mechanism is what was tested. If that matters to a future number, test it.
- **The agent still never performed a remediation.** It holds four read-only tools. This settles
  whether the *label* was true, not whether the agent could carry the fix out.

Revisit if: a second scenario turns out to have two working fixes and the pattern needs a rule
rather than a field, or a remediation in `also_correct_remediation` stops working on a changed
world.
