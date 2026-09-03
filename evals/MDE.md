# Minimum detectable effect — what this catalog can and cannot measure

**Checked in before the first ablation runs**, which is T4.6's requirement and the only
point at which a table like this is honest: computed afterwards, it becomes a description of
whatever was found.

**Generated** by `evalharness.variance.table()` — regenerate with
`uv run python -c "from evalharness import variance; print('\\n'.join(variance.table()))"`.
Do not hand-edit; the numbers are derived and the derivation is the point.

## Two quantities, and the plan's table mixes them

The execution plan states *"10 scenarios ≈ 20pp (directional only, never publish a number);
30 ≈ 10pp; 30 paired at R=5 ≈ 6–7pp"*. Computing them found those are **not all the same**
**quantity**:

| the plan's figure | what reproduces it | computed |
|---|---|---|
| 10 scenarios ≈ 20pp | 95% CI **half-width**, paired, ρ = 0.8 | 19.6pp |
| 30 ≈ 10pp | the same half-width at n = 30 | 11.3pp |
| 30 paired at R=5 ≈ 6–7pp | **MDE at 80% power** — a stricter quantity | 7.2pp |

A CI half-width is what a comparison can **resolve**. An MDE at 80% power is what it can
**reliably detect**, and it is larger by (z_α + z_β)/z_α = 1.43.
Quoting one under the other's name would understate what this catalog can detect by 43%, so
both columns are printed below. **The plan's numbers are not wrong** — two are half-widths and
one is an MDE, and this table names which is which rather than picking the flattering one.

## The table

Paired comparison, worst-case baseline p = 0.5, two-sided 95%, 80% power.

| scenarios | R | effective | CI half-width | MDE (80% power) | at rho=0.5 |
|---|---|---|---|---|---|
| 10 | 1 | 10 | 19.6pp | 28.0pp | 44.3pp |
| 10 | 3 | 30 | 11.3pp | 16.2pp | 25.6pp |
| 10 | 5 | 50 | 8.8pp | 12.5pp | 19.8pp |
| 18 | 1 | 18 | 14.6pp | 20.9pp | 33.0pp |
| 18 | 3 | 54 | 8.4pp | 12.1pp | 19.1pp |
| 18 | 5 | 90 | 6.5pp | 9.3pp | 14.8pp |
| 30 | 1 | 30 | 11.3pp | 16.2pp | 25.6pp |
| 30 | 3 | 90 | 6.5pp | 9.3pp | 14.8pp |
| 30 | 5 | 150 | 5.1pp | 7.2pp | 11.4pp |

## What the assumption is carrying

**ρ = 0.8 is assumed and has never been measured here.** It is the correlation
between two configurations on the same scenario, and pairing is worth more the more a
scenario's difficulty carries across pipelines — in this catalog it usually does;
`shipping-quote-misconfig` has been wrong under three of them. The final column shows the same
MDE at ρ = 0.5 so a reader can see how much of the answer the assumption supplies: at n = 30,
R = 5 it is the difference between 7.2pp and 11.4pp.

**The measurement that would settle it** is the same catalog under two configurations with
repeats — which is exactly what T4.7's baseline suite produces, so ρ becomes measurable the
first time B1 or B2 runs at R ≥ 3.

## The catalog today

18 scenarios, of which 15 are runnable (three carry `INVALID.md`). Split dev/holdout, a
paired comparison on the dev set is **n ≈ 10**.

| at n = 10 | R = 1 | R = 3 | R = 5 |
|---|---|---|---|
| MDE (80% power) | 28.0pp | 16.2pp | 12.5pp |
| cost at $0.70/run | $14 | $42 | $70 |

Cost is for **both arms** of a paired comparison at dev sweep 8's measured $0.70 a run. This
is the plan's *"cost flagged, not hidden"*: R = 5 is a 5× spend multiplier, and the tiering
exists to confine it to comparisons that get published.

**The consequence, stated plainly.** At the catalog's current size a single-run comparison
cannot detect anything smaller than **28pp**. Every ablation result this
repository can currently produce at R = 1 is directional only, and a delta below its MDE is
reported as *"no measurable effect at this catalog size"* — which the plan calls stronger
interview material than a fabricated 3-point win, and it is right.
