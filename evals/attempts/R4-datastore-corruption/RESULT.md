# R4 — `datastore_corruption` rehearsed through the injector — RESULT

**Run 2026-09-24 07:21:39 → 07:38:03 UTC, \$0**, `v2-cart-store-corruption`, protocol
`evals/runs/REHEARSALS-T7.0.md` with its addendum; whole world. Terminal verbatim in
`transcript.txt`. **No page in twelve minutes, and the reason is the injector's**: its loop
never ran the sweep (§7). Recorded as measured; fixed in 0147; run again as **R4b**.

| | verdict | from the record |
|---|---|---|
| **INJECTS** | **no** | `start` at 07:21:39 reported one verified sweep (731 keys) and a loop every 50 ms. Twenty-four quiet polls; at minute twelve `cart` 0.00 % / p95 5 ms / 4.16 req/s, `checkout` 0.00 % / 31 ms / 1.89 — the pre-state's numbers. A4b, by hand at the same cadence, paged `checkout` at +4:45. The loop's script read `$STOP`, `$SCRIPT`, `$FIELD`, `$BYTES` while `sh -c` had been handed them as `$1`–`$4`, so it ran `EVAL "" 0 "" ""` every 50 ms with its output discarded; the one sweep that did run hit only dead carts, as A4's 5-second sweep did. The fault the class is named for was applied once, at 07:21:39, to nothing live |
| **VISIBLE** | **nothing to see — correctly** | `logql_query cart`: ordinary `GetCartAsync`/`EmptyCartAsync` lines, no `Can't access cart storage`; `logql_query checkout`: nothing; `trace_query checkout --errors`: no traces; `cart` error ratio: no error series. The tools reported a healthy world because it was one. A read-back that says nothing when nothing is wrong is the tool working |
| **RESTORES** | **half** | `stop` at 07:38:03 placed the stop file and ran `FLUSHALL`; `status` empty; second `stop` *not active*. **The loop did not end**: `[ ! -f "" ]` is always true, so the injector's own restore could not stop what its own start had launched, and `docker top` showed it still sweeping nothing at 07:38. Removed by hand before R4b. The restore's contract — stop the loop, then flush — was only half performable on the loop as written |
| **A SCENARIO MAY BE AUTHORED** | **not from this run — R4b decides** | The mechanism is A4b's and A4b paged; the injector's carriage of it did not. Fixed the same hour: positional inputs, the payload as hex decoded in Lua (the old `\xff\xff\xff\xff` reached the CLI as sixteen ASCII characters), a heartbeat file the loop rewrites every pass and `inject` reads before it reports success, and `test_corruption_loop_runs_under_a_real_sh`, which runs the script under the host's `sh` — the only kind of test that could have caught a loop that was a no-op. |
