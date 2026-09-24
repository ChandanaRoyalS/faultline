# R1 — `feature_flag` rehearsed through the injector — RESULT

**Run 2026-09-24 02:24:25 → 02:45:59 UTC, \$0**, `v2-product-catalog-flag-failure`, protocol
`evals/runs/REHEARSALS-T7.0.md`. **Read `transcript.txt`'s provenance note first**: the live
terminal paste was lost before the write-up, so the record is the clock readings kept from it plus
the same window re-read from the stores (`replay.py` for the alert timeline and the 02:36 shape,
`evalharness.readback` for the tools). The verdicts below cite only what one of those shows.

| | verdict | from the record |
|---|---|---|
| **INJECTS** | **yes** | The injector's `start` at 02:24:25 produced A1's shape: `ServiceHighErrorRate/frontend-proxy` at 02:29:56 (**+5:31**; A1 +5:37), `/frontend` at 02:30:26 (**+6:01**; A1 +6:07), and — new against A1 — `/product-catalog` itself for three ticks, 02:31:30–02:32:30, its ratio peaking at **5.64 %** over the 5 % line where A1's stayed at 4.63 %. Shape at 02:36: `frontend` 6.91 %, `frontend-proxy` 7.27 %, `product-catalog` 4.20 %; p95 unchanged everywhere (`product-catalog` 5.7–8.4 ms). Same rule, same services, within 10 s of the attempt. The culprit paging is the one difference and is recorded, not tuned: A1 read the one-product dilution as keeping `product-catalog` under the line; the same flag on the same service crossed it here, so the denominator is the load generator's mix at that minute, not a constant, and a scenario on this class may not lean on the culprit staying quiet |
| **VISIBLE** | **yes on (a) and (c); (d) reachable, not read on this window** | **(a)** the promql curves through `evalharness.readback`: `frontend` max 8.97 %, `product-catalog` max 5.64 %. **(c)** `logql_query frontend` returns the flag's own words — `Error: 13 INTERNAL: Error: Product Catalog Fail Feature Flag Enabled` at **02:24:29**, four seconds after `start` — and at 02:36:22 the flag's second face, `failed to prepare order: failed to get product #"OLJCESPC7Z"`, checkout failing on the same product; `logql_query product-catalog` returns **nothing** in 22 minutes, A1's finding 2 now measured through Loki. **(d)** `trace_query` failed live at 02:36 — Tempo was found exited 137 at 02:58:54 (Q91) — and after the recreate reads only what was emitted since, so the flag's error span was **not** read on this window. That the tool path reaches Tempo at all was then shown at 03:44: ten `frontend` traces, 186 spans, Tempo 284 MiB of 1 GiB after the query that killed it before. **(b)** `change_history`: *no change log configured* — unavailable, as fixed in advance, never a record |
| **RESTORES** | **yes** | `stop` at 02:36:28 → *reverted*; `status` → *no active injections*; second `stop` → *is not active; nothing to revert*. Both alerts clear at the 02:39:00 tick (live: 02:38:59, **+2:31**; A1 +2:07); quiet through 02:46:00, seven minutes |
| **A SCENARIO MAY BE AUTHORED** | **yes** | Injects, restores, idempotent, and (a) and (c) come back through the agent's tools. **Two debts travel with it**: the flag's error span read back through `trace_query` during a live flag — owed since A1 (*"stated from source, not yet read back from Tempo"*), still owed, collectable in a two-minute start/read/stop with no page; and this record's own provenance, which is the stores' and not the terminal's |

---

## Addendum — the (d) read on a live flag, 2026-09-24 03:54:53 → 04:00:05

Ninety seconds of flag through the injector, one `trace_query product-catalog --errors` through
`evalharness.readback`, stop, status, four quiet minutes (`transcript.txt` §4). No page, as the
arithmetic said. **The injector's `start` and `stop` text is now on the record**, which R1's lost
paste was not: *flagd: productCatalogFailure defaultVariant 'off' -> 'on'* in the bind-mounted
`demo.flagd.json`, *no compose change and no change record*, and the restore to *'off'*.

**(d) is read, and it is half of what the table asked for.** `trace_query` returned **ten** error
traces on `product-catalog` in the ninety seconds, and in the one rendered, every hop from
`load-generator/GET` down is `ERROR` and the degrading hop is named as
`frontend/grpc.oteldemo.ProductCatalogService/GetProduct -> product-catalog/oteldemo.ProductCatalogService/GetProduct
0.1ms (error)` — the culprit's own server span, in error, in 0.1 ms. That is the error span the
table's (d) names, reachable through the agent's tool. **The flag's message is not carried.** Two
reasons, both properties of the tool and not of the world: `spantree.render` prints no status
message for any span (only the `ERROR` flag), and `MAX_DEPTH = 6` — set for v1's
`loadgenerator → frontend → checkout → cart → redis` — is one level short of the culprit on v2's
path, where `frontend-proxy` adds two hops and the Next.js frontend two more, so the
`product-catalog` span itself is the `1 deeper span(s) elided` and appears only in the hop line.
The message *does* reach the agent, through (c): `logql_query frontend` carries it verbatim
(§2). **Q94** records the tool finding; the R1 verdicts stand as written, with (d) now *read*
rather than *reachable*, and A1's RESULT gets the addendum it asked for.
