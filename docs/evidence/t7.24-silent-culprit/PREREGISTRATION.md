# T7.24 pre-registration — the first investigation of a silent culprit

**Written and committed before the run.** One scored run of `shipping-quote-misconfig` at stamp
`1b0e7cbb4c47`, T4.7 budget (`changes` 8, others 4), full protocol, judged.

## Why this scenario is different from every other in the catalog

T7.22 measured its evidence shape, and nothing else recorded has it:

- **The faulty service produces no errors of its own.** `shippingservice`'s error ratio never
  leaves zero for the whole fault. It never appears in an error query and never approaches a rule.
- **Its 126 log lines are ordinary traffic.** Every one is an incoming `GetQuoteRequest` at the
  usual rate. No error line, no retry, and **no mention of the address it cannot reach**. They are
  **exculpatory, not diagnostic**: they prove shipping is alive and being asked for quotes, which
  rules out the first thing anyone checks and says nothing about what is wrong.
- **`change_history` is the only class that names it at all.**
- The page says **checkoutservice** — `ServiceHighErrorRate`, the sole alert at fire.

Every other dev scenario has its fault and its alert on the same service, or has logs that carry
the failure. This one separates them.

## Registered predictions

Each is falsifiable, and the ledger below is scored as written.

| # | prediction | what would falsify it |
|---|---|---|
| **P1** | The agent **localizes first to `checkoutservice`** — triage's blast radius and starting service name it, because it is the only thing alerting. | Triage starts anywhere else. |
| **P2** | The agent **does reach `shippingservice`** during the investigation. | No dispatch names shipping and no finding cites it. |
| **P3** | It reaches it **by the dependency graph**, not by a metric or log signal — because no metric or log signal points there. Concretely: the planner names shipping as a downstream of checkout, or the synthesizer reaches it from the graph. | It reaches shipping via a metric or log finding that flags shipping directly. |
| **P4** | **`change_history` on `shippingservice` is what identifies the fault.** The verdict's cited evidence includes a change-history result for shipping. | The verdict identifies the fault without a shipping change-history citation. |
| **P5** | The verdict names **`bad_config`** and **`shippingservice`** as root cause. | Any other class, or any other service named as the cause. |
| **P6** | Fix class **`config_revert`**. | Anything else. Note `restart` is the plausible rival and is *wrong* here — restarting shipping under the bad address changes nothing. |

**The registered risk, and the reason this run is worth making.** The agent may localize to
checkoutservice, find checkout healthy and unchanged, and **stop there** — either abstaining or
naming checkout. T4.14's return-to-locus instruction exists to carry it from where the page points
to where the fault is; this scenario is the sharpest test of it in the catalog, because the locus
of the *alert* and the locus of the *fault* are different services and no signal bridges them
except the graph and change history.

**What would show return-to-locus does not carry the agent from an alerting caller to a silent
culprit:** the run answers with `checkoutservice` as the faulty service, or abstains (`unknown`),
**while never dispatching a specialist against `shippingservice`.** That is the falsifying result,
and it is a real possibility — P2 failing is the outcome this experiment is designed to be able to
see.

**Also registered as a distinct near-miss:** reaching shipping, finding no errors in its metrics
and nothing in its logs, and concluding shipping is *healthy* — then answering checkout or
abstaining. That would show the agent reached the right service and was defeated by exculpatory
evidence, which is a different failure from never arriving.

## Two things to verify and report regardless of outcome

**Contamination.** The corpus now contains this scenario's own narrative as a dev document (T7.22
seeded 8 documents, 40 chunks). `exclude_origin` must fire. **Verify from the trajectory's
retrieval rows** that `scenario:shipping-quote-misconfig` was excluded, and report which past
incidents came back instead. A run where the filter did not fire is **invalid**, not annotated
(ADR-0008 axis 2).

**Reachability.** T7.22 found and fixed a recorder bug that wrote `target_log_lines: 0,
none_can_answer: true` onto this bundle. This is the **first run scored against a bundle whose
reachability field was derived correctly** (`["logs"]`, 126 lines). Note whether the scored report
carries it.

## Scope

**One run is one observation.** Whatever happens, it does not establish a rate, and the writeup
will say so. It cannot distinguish a capability from a lucky draw, and n=1 against a world whose
timings vary by 53% on an unchanged scenario is not a measurement of anything but this run.
