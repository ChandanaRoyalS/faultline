# T2.6 evidence — the four tools against the live world

One `cart-redis-misconfig` injection, all four tools queried during the fault, and the
reversal read back after it. The run found one defect that no hermetic test had reason to
look for, and that is the useful part.

| | |
|---|---|
| injected | 2026-08-25 **22:42:32Z** |
| reverted | 2026-08-25 **22:44:35Z** |
| tools queried | 22:44:15Z, over a 15-minute window opening 22:29:15Z |
| change log | `change_records` in `faultline-postgres-1` |

## Files

- **`envelopes.txt`** — all four results during the fault, as an agent receives them.
- **`after-revert.txt`** — `change_history` again after the revert.

## Schema

`change_records` was created explicitly before the run:

```python
PostgresChangeLog(psycopg.connect(ToolSettings().postgres_dsn)).create_schema()
```

`faultline-inject` also creates it on first use, through `_change_log()`, which swallows
every failure — an injection must not fail because the change log is down. **That silence is
the failure mode for a smoke**: an unreachable Postgres yields a successful injection and no
record, with nothing on stderr. Creating it up front is how you find out before the run
rather than after.

## The change record lands in the same second as the injection

Injected at `22:42:32Z`. The record is stamped `22:42:33.116952+00:00` and was already in
Postgres when the command returned — it is written synchronously inside `Engine.start`, after
the state file and before the result. There is no polling interval to wait out and no
collector to catch up.

## The four envelopes

Every result arrived delimited, typed, and labelled untrusted, with a closing tag carrying
its own random id:

```
<tool_result id="tr_dff59750f4ef" tool="promql_query" trust="untrusted" source="prometheus"
             empty="false" truncated="false" window="…22:29:15…..22:44:15…">
query: sum by(service_name) (rate(calls_total{service_name="cartservice"}[2m]))
1 series
  {service_name=cartservice} min=0.6783 max=4.39 n=61
</tool_result:tr_dff59750f4ef>
```

| tool | source | empty | truncated | content |
|---|---|---|---|---|
| `promql_query` | prometheus | false | false | 1 series, 61 points |
| `logql_query` | loki | false | **true** | 15 lines of a capped window |
| `trace_query` | jaeger | false | **true** | 200 spans |
| `change_history` | change-log | false | false | 1 change |

The change envelope during the fault:

```
<tool_result id="tr_6a4bf9f72993" tool="change_history" trust="untrusted" source="change-log"
             empty="false" truncated="false" window="…">
service: cartservice
1 changes
  2026-08-25T22:42:33.116952+00:00  platform-automation  environment updated: REDIS_ADDR updated on cartservice
      None  ->  REDIS_ADDR=redis-cart:6380
</tool_result:tr_6a4bf9f72993>
```

`REDIS_ADDR=redis-cart:6380` is the value the investigation turns on — `cart-redis-misconfig`'s
narrative reads it directly — so the record carries the *value* and not merely the fact that
an environment variable moved.

## The reversal pairs exactly

After the revert, the same query returns both records, and the second inverts the first:

```
2 changes
  22:42:33  platform-automation  environment updated:  None -> REDIS_ADDR=redis-cart:6380
  22:44:35  platform-automation  environment reverted: REDIS_ADDR=redis-cart:6380 -> None
```

The reversal's `before` is the injection's `after`, and its `after` is null. An operator
reading this sees a configuration change and its undo, with nothing naming what caused either.

## The leak check, on live rendered output

Run against `after-revert.txt`, the actual text an agent would have received:

```
banned vocabulary found: none
scenario id present: False
fault class present: False
```

`platform-automation` is the actor throughout. Nothing in the surface says `inject`,
`fault`, `faultline`, `bad_config`, or `cart-redis-misconfig`.

## Found by the smoke: truncation kept the wrong end of the window

**Fixed in this branch.** The log result was correctly flagged `truncated="true"` and was
investigatively useless:

```
2026-08-25T22:29:16.110522+00:00  AddItemAsync called with userId=67d6a324…
2026-08-25T22:29:16.113375+00:00  GetCartAsync called with userId=67d6a324…
…
2026-08-25T22:29:22.550661+00:00  GetCartAsync called with userId=6babef36…
```

Fifteen lines spanning **six seconds**, at the very start of a fifteen-minute window — and
the injection was at 22:42:32, **thirteen minutes later**. Every retained line is healthy
pre-onset traffic. An agent asking what happened to cart would have received an accurate,
correctly-labelled answer to a question nobody asked.

The cause was `direction="forward"` on the Loki request. Loki applies the cap itself, so the
direction has to be right on the request — sorting afterwards cannot recover lines that were
never sent.

`trace_query` had the same defect and had not been observed hitting it: it flattens whole
traces and truncated to 200 spans in whatever order the API happened to list them, which in
this run was also the oldest end.

Both now truncate from the newest end and display chronologically — different questions, and
that one has to be answered first. `tests/test_tools.py` pins both, plus the request
direction, since the request is where the loss happens.

**Why no hermetic test found it.** Every fixture had fewer lines than the cap, so nothing was
ever truncated. The tests asserted `truncated` was *reported* correctly and never asked
*which* lines survived. It needed a real window with more data than the limit, which is what
a live run is for.

## What this smoke did not exercise

- **A fully-developed fault window.** The promql result shows `cartservice` still serving —
  `min=0.6783` req/s across 61 points, never zero. The tools were queried 103 seconds after
  injection, and cart had not yet gone quiet. So **no tool has been read against a fault at
  its worst**; every result here describes a world in transition. The first agent run will be
  the first time that happens.
- **Empty and error against live services.** Both are unit-tested and neither occurred here:
  every tool returned data, and no endpoint was down. The states that matter most for the
  negatives in eight of ten narratives have not been seen live.
- **`change_history` returning nothing.** The load-bearing case in four narratives is a
  service with no changes in the window. This run only ever asked about the one service that
  had one.
- **The `promql_query` endpoint fix.** `ToolSettings.prometheus_url` was accepted and ignored
  until after this run; the values were identical so the output above is unaffected, but the
  configured-endpoint path was not what produced it.

## Reproducing

```bash
uv run faultline-inject start cart-redis-misconfig
# …wait, then query the four tools over a window opening before the injection…
uv run faultline-inject stop cart-redis-misconfig
```

The exact scripts are in the commit that added this directory. Note the window must open
before the injection: three of the ten rehearsed narratives read logs from before onset, and
`shipping-wrong-image` says the pre-onset stream is where its investigation breaks open.
