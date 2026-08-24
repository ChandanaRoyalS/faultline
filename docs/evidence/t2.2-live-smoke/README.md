# T2.2 live smoke — a backlog drain, a crash, and a clean recovery

The orchestrator's first run against a live world. It is written up as it happened rather
than as it was meant to, because the interesting half is the crash: the run found a defect
no test could have, and then the recovery proved a design claim ADR-0016 had only asserted.

| | |
|---|---|
| scenario | `cart-redis-misconfig` (bad_config, dev), injected twice |
| stream | `faultline:alerts` on `faultline-redis-1` |
| incidents | `faultline-postgres-1`, tables from `--create-schema` |
| result | 2 incidents, 8 episodes, 16 applied events, **0 duplicates** |

## Files

- **`crash.log`** — the first run's entire stdout and its traceback.
- **`final-state.txt`** — `psql` after the second run: both incidents, all eight episode
  attachments, and the `applied_events` count.
- **`stream-16-events.txt`** — `XRANGE faultline:alerts - +`, sixteen entries.
- **`recovery.log`** — empty, and see "What the logs do not show" below.

`final-state.txt` is `psql`'s output with its trailing header padding stripped: the repo's
pre-commit hooks trim trailing whitespace, and they ran on it. No value changed - only the
spaces `psql` pads column headers with - but it will not byte-match a fresh run, and that is
worth knowing before anyone diffs it against one.

## First start: the backlog drained itself, unprompted

The consumer group is created at `id="0"`, so a new group starts at the beginning of the
stream rather than at the tail. Nobody asked it to do anything with history; that is simply
what a group created at `0` does.

What was sitting there was the eight events T2.1's receiver had published that morning
(`docs/evidence/t2.1-live-smoke/`), hours earlier, from a different process. The orchestrator
read them and produced **exactly the outcome ADR-0016 predicted**:

```
8e8abd45-3e37-48c0-aa52-c5403bf6ae83 | resolved | alerts_resolved
  checkoutservice  starts 11:12:00.583   resolved 11:15:40.662
  frontend         starts 11:12:00.583   resolved 11:16:40.664
  loadgenerator    starts 11:12:00.583   resolved 11:16:40.663
  emailservice     starts 11:15:45.583   resolved 11:16:55.645
```

One incident, four episodes, `emailservice` — the post-revert recovery alert, starting 3m45s
after the other three and 15 seconds after `checkoutservice` had already resolved — **joined
rather than opening a second incident**, and the incident resolved at the last resolution.

Two things about that are worth separating. The replay tests in `tests/test_orchestrator.py`
prove the *logic* on the same eight events. This run proved the *wiring*: a consumer group,
a real stream, JSON decoded off Redis, rows written to Postgres, on data that was never a
fixture and was published before the code that consumed it existed.

Note also the timestamps. `opened_at` is `11:12:10.676697` — the T2.1 event's own
`received_at`, not the time the orchestrator got to it. Incident times come from the events,
so draining a backlog reconstructs an incident as it happened rather than stamping it with
replay time. That is what makes processing history meaningful rather than merely possible.

## …and then it died on its first empty read

```
consuming faultline:alerts as orchestrator/orchestrator-1
Traceback (most recent call last):
  ...
  File ".../faultline/orchestrator/consumer.py", line 69, in read
    response: Any = self._client.xreadgroup(
  ...
redis.exceptions.TimeoutError: Timeout reading from socket
```

That is the whole first run: one line of stdout, eight events applied silently, and a
traceback. The backlog came back instantly because a non-empty `XREADGROUP` returns at once.
The next read found nothing, blocked, and the client gave up before the server answered.

**The cause was an exact tie.** redis-py 8.1.0 defaults `socket_timeout` to **5 seconds**;
this module's `block_ms` defaulted to **5000**. The socket was configured to stop waiting at
precisely the moment the server would have replied with an empty result. The race was not
close and did not depend on load - it was deterministic, and it lost every time.

**No test could have found it, and that is the part worth keeping.** The failure exists only
when there is nothing to read, and nothing to read is the healthy steady state of this
system. Every fixture-driven test hands the consumer an event, because a replay source
always has one; the suite had no way to produce an empty stream, and a full backlog run
masked it for the same reason. It was reachable only by running the thing with nothing to do.

The fix is in the client rather than in `block_ms` — shrinking the block would have moved the
race, not removed it. `RedisEventSource.connect` now derives the socket timeout from
`block_ms`, the source owns `block_ms` instead of taking it per call so the two numbers
cannot be set independently, and construction refuses a client that would lose the race. That
last part is what made it testable without an empty stream.

**A second blocking bug fell out of reading the same call path.** `block_ms=0` was passed
straight through to redis-py, and `XREADGROUP BLOCK 0` blocks *forever* — so `--once` would
have hung on an empty stream instead of returning. `read()` now takes whether to block, not
how long.

## Between the runs: eight more events, and nobody listening

A second `cart-redis-misconfig` injection ran at noon while the orchestrator was dead. Ingest
was still up, so it received, deduplicated and published all eight events normally. They sat
in the stream, unread, in a consumer group with a pending entry list that was empty and a
last-delivered id that had not moved.

This was not arranged. It is what a crash looks like when the producer outlives the consumer,
and it is the condition ADR-0016's consumption design was written for.

## Second start, after the fix

The consumer resumed from where the group had stopped, drained the eight noon events, and
built the second incident:

```
235fab65-7d9f-4c4e-b1e3-39feab010f90 | resolved | alerts_resolved
  frontend         starts 12:04:00.583   resolved 12:10:10.687
  loadgenerator    starts 12:04:00.583   resolved 12:10:10.687
  checkoutservice  starts 12:04:15.583   resolved 12:09:25.669
  emailservice     starts 12:08:45.583   resolved 12:10:25.663
```

Then it sat on an empty stream through repeated blocking reads until it was killed — which is
the behaviour the fix was for, and the only way to observe it is to do nothing for a while.

`emailservice` reproduced a third time: fired 4m45s after the incident's first alert, joined,
and resolved last of the four. Across three injections now
(`t2.1-webhook`, `t2.1-live-smoke`, this one) the recovery artifact has appeared every time.
The noon run differs from the morning in one detail worth noting for anyone comparing them:
`checkoutservice` alerted 15 seconds *after* frontend and loadgenerator rather than with
them, so the three-at-once opening is not guaranteed.

## What this demonstrated beyond the fix

**Crash recovery with no event loss and no duplicates.** Sixteen events published, sixteen
applied, two incidents, eight episodes, and `applied_events = 16` with no repeated
`(episode_key, status)` anywhere. The consumer died mid-run and came back to a stream holding
eight unread events, and the count is exactly right on both sides.

That is ADR-0016's consumption design working rather than being asserted:

- **Write, then ack.** The ADR argued that since Redis and Postgres share no transaction, the
  only choice is which failure to prefer — a redelivered event that was already applied is a
  no-op, a lost one is not. The crash exercised that ordering for real. Nothing was acked
  that had not been written, and nothing was written twice.
- **An event is processed when its state change is durable, not when the investigation
  finishes.** Incident one was complete in Postgres before the process died, on a stream
  entry that had been acked. Nothing about the crash touched it.
- **Idempotency on `(episode_key, status)`.** It cost nothing here because no redelivery
  actually occurred - the crash fell between reads, not between a write and an ack. It is
  still the reason the write-then-ack choice is safe, and this run is not evidence that it
  works. That case remains tested and unobserved.

## What the logs do not show

`recovery.log` is empty, and that is an artifact of how the run was captured rather than of
the run. Python buffers stdout when it is redirected to a file, and the second process was
killed rather than allowed to exit, so its one startup line never flushed. The evidence for
the second run is `final-state.txt` and the stream dump, not the log. Anything that captures
a long-running consumer again should run it with `-u`, or the next crash will take its
context with it.

## Still not exercised

- **The dedupe path was never hit.** Sixteen deliveries, sixteen distinct transitions. No
  repeat notification, no Alertmanager retry, no stream redelivery. Both dedupe mechanisms
  remain tested and unobserved in production.
- **Correlation was never asked a hard question.** Both incidents were the only live incident
  at their time, so `TimeOverlapPolicy` had nothing to get wrong — and it structurally cannot
  have, since it joins any firing to any live incident. See ADR-0016's consequences: the cap
  is unreachable until T2.4's `DependencyPolicy` can decline.
- **The cap and its queue never ran.** Same reason. `max_concurrent` was 3 and the system
  never held more than one incident.
- **No state past `TRIAGING`.** Both incidents opened, were admitted, and resolved from
  `TRIAGING`, because T3.x does not exist to advance them. The seven states after it have now
  been in a real database exactly zero times.
