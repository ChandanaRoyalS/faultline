# RESULT - T7.2 dev pilot

Read against [`PREREGISTRATION-T7.2-pilot.md`](../../runs/PREREGISTRATION-T7.2-pilot.md), part B
and Addenda 3 to 8. Run 2026-10-03, 01:46-05:33 UTC, on the deployment. Evidence is in
[`docs/evidence/t7.2-pilot/`](../../../docs/evidence/t7.2-pilot/) (`t72-pilot-b-*`).

**The pilot is not a measurement of either agent.** It has three problems at R = 1 and no pass-rate
prediction, as registered. What it measures is whether the run works, what it costs, how long it
takes, and what has to change first.

## The six attempts

| # | problem | agent | judged | score | start to exit | agent's stage |
|---|---|---|---|---|---|---|
| 1 | `edge_request_filter_cpu_saturation` (shop) | Faultline | wrong: `frontend`, truth `frontend-proxy` | 0 | 19.7 min | 518 s |
| 2 | same | Claude Code | right | 89 | 11.7 min | 316 s |
| 3 | `update_incompatible_correlated` (hotel) | Claude Code | right | 89 | 8.5 min | 140 s |
| 4 | same | Faultline | wrong: `mongodb-rate`, a freeze; truth: an incompatible image on all six MongoDBs | 22 | 12.1 min | 457 s |
| 5 | `k8s_target_port-misconfig` (social) | Faultline | wrong: *"not established"*; truth: `user-service`'s `targetPort` | 0 | 26.3 min | 1,329 s |
| 6 | same | Claude Code | right | 100 | 7.4 min | 96 s |

Scores are SREGym's judge's (`t72-pilot-b-results/`). **No comparison is drawn from three pairs.**
The point of the table is what follows from Faultline's records: on every problem, its tools
failed before its reasoning could be tested.

## The predictions

| prediction | held? |
|---|---|
| every attempt ends with a submission; Faultline's says `Faultline reached no verdict.` at most once | **held**: 6 of 6 submitted; Faultline reached a verdict all three times |
| Faultline's install in the box: 60 to 120 s | **held**: 66, 60 and 60 s |
| Faultline's opening: alarms on Hotel Reservation, the front-door fallback on Social Network, Astronomy Shop as the dev read finds | **held**: <br>- hotel: nine alarms, `KubeDeploymentReplicasMismatch` on all six MongoDBs among them; <br>- social: the fallback after six evaluations; <br>- shop: the startup crash loop on `product-catalog` and `ServiceHighErrorRate` on `load-generator` |
| Faultline's cost per attempt: $0.30 to $1.50 | **held**: $0.57 to $0.69, from its recorded tokens (below) |
| the baseline's cost per attempt: $0.50 to $3.00 | **held**: $0.51 to $0.93, from its recorded tokens |
| time per attempt, deploy to submission: 10 to 40 minutes | **held for Faultline; wrong, faster, for two of the baseline's three**: Faultline took 12.1 to 26.3 minutes start to exit, and Claude Code 7.4, 8.5 and 11.7 |
| total spend: $5 to $15, under the cap | **wrong, lower**: $3.89 for the two agents from their tokens, plus the judge's six calls and `judge-check`. The owner read the console as well under the cap |
| the world: no alert, none of the 35 restarted, MemAvailable above 5 GiB throughout | **wrong on all three**: <br>- one alert fired, 04:34:34-04:36:34; <br>- `email-service` restarted at 04:34:49; <br>- MemAvailable fell to **4.04 GiB** (02:31, attempt 1), and stayed under 5 GiB for 27 samples, all during the two shop attempts |
| the key: 0 occurrences in the collected results | **held**: 0 in `collect`'s archive, 0 in every record; shredded on the VM |

**About the world.** `email-service` was at 244 of its 250 MiB limit when the sampler started, and
had restarted once already, on 2026-10-01, before the pilot. So the likeliest cause is its own
limit, not the host. The host's MemAvailable stayed above 8.0 GiB while the alert fired. **Whether
the pilot caused it is not established.** No incident opened.

## Cost

Computed from the tokens each agent recorded, at the published prices (Opus 5: $5 per million
input, $25 output; Sonnet 4.6: $3 input, $15 output, $0.30 cache read, $3.75 cache write):

| agent | attempt | tokens | cost |
|---|---|---|---|
| Faultline (Opus 5) | 1 / 4 / 5 | 65,114 / 48,120 / 57,691 in; 14,122 / 13,217 / 15,948 out | $0.68 / $0.57 / $0.69 |
| Claude Code (Sonnet 4.6) | 2 / 3 / 6 | 17,624 / 5,690 / 7,821 out; 1.58 M / 0.88 M / 0.92 M cache reads | $0.93 / $0.51 / $0.51 |

- **Faultline: $1.94. Claude Code: $1.95.**
- The judge's calls are not in these figures.
- **The console's figure for the key is the authority**, and it replaces these when the owner
  records it.
- Faultline's tools failed on most calls (below). With them fixed, its tokens per attempt will
  differ, because results are longer than errors.

## The run, projected from the pilot

At the pilot's rates, the scored run's 108 problems × R = 3 × 2 arms = 648 attempts would take:

- **cost**: about **$420** for the two agents (324 × $0.65 each), plus the judge;
- **time**: about **154 hours sequential**, 6.4 days: Faultline about 19.4 minutes an attempt and
  Claude Code about 9.2.

Both numbers carry the defects below, so **neither is the number to approve on**. The opening's
slowness alone (finding 4) adds up to 17 minutes to each Faultline attempt on an application
without alarms.

## What the pilot found, for the owner before the scored run

Each item says whether it is the adapter's defect or the benchmark's world, and whose decision a
fix is. **The plan's T7.2 requires "the agent under test is the real one"**, so a fix belongs in
the adapter, never in Faultline's own behaviour.

1. **The log selector is refused: an adapter defect.**
   - `pod_pattern`'s `re.escape` writes `\-`, which Loki and Prometheus refuse.
   - It failed every log query and the memory query on hyphenated names, in all three Faultline
     attempts.
   - **The fix is measured**: the probe's unescaped selector was accepted.
   - Addendum 1 makes the selector's fix the owner's decision.
2. **The change commands' answers are cut: an adapter defect.**
   - SREGym's kubectl server cuts every answer at 10,000 characters, and refuses pipes.
   - All nine `change_history` calls failed.
   - The answers measured 213,062 (ReplicaSets), 50,193 (StatefulSets and revisions) and 328,279
     (events) characters, and **one object alone can pass the cut**.
   - A fix must ask for named fields only.
   - **It cost the answer twice**: attempt 4's truth was an image change and attempt 5's a Service
     change, both what the change log exists to show.
   - The change commands are frozen, so this is the owner's decision.
3. **There is no metric history to compare: the benchmark's world, not a defect.**
   - SREGym deploys Prometheus with each attempt, so it holds about three minutes before the fault.
   - Faultline's baseline comparison (T3.2b: onset − 30 min, against the window before) has no
     baseline.
   - Changing Faultline's windows would be tuning the agent under test. **The owner decides whether
     anything changes, and the report says so either way.**
4. **The opening is slow: an adapter defect, about time only.**
   - Each MCP call took about 15 s. An evaluation makes about ten.
   - The opening took 2.6 minutes on the shop and on the hotel, and **17.1 minutes** on the social
     network, through six evaluations to the fallback.
   - Attempt 5's agent stage was 1,329 s of the 1,800 s timeout. **A slower box would have timed
     out.**
   - Why a call takes 15 s is not established.
5. **`latency-p95` read 0.005 for `frontend` and `product-catalog`, in a family named in milliseconds: not established.**
   - It needs the duration histogram's bounds in SREGym's collector.
6. **The shop's startup crash loop seeds the shop's incidents.**
   - Recorded in Addendum 2. Attempt 1 went to `product-catalog` first.
   - It will recur on the shop's 41 problems. The alarms are frozen.
7. **Operation:**
   - the Mac waits only on an attempt's `exit` line (Addendum 6);
   - the script is copied only between stages (Addendum 8);
   - `cleanup` needs `sudo` for Claude Code's root-owned logs;
   - each Faultline attempt's record is taken before the next (Addendum 7);
   - the shop's attempts leave about 4 GiB of headroom on the host.
8. **The repeat count.**
   - The execution plan's T4.6 sets **R = 5** for scored comparisons. The run registered **R = 3**,
     the owner's choice, after SREGym's paper.
   - Raised by the owner's check against the plan on 2026-10-03, and left for the owner's go.

## Next

The run's step 4: **the owner's go**, with an addendum to the run's registration for whatever is
fixed, registered before anything runs. Then the short re-check of Faultline on the three dev
problems that the owner asked for (Addendum 6), and then the scored run.
