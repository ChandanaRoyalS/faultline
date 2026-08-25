# T3.2 smoke — a trajectory round-trips through Postgres byte-identically

No model call, no world. A synthetic trajectory — dispatches, a real rendered envelope, and a
retrieval with its exclusion — written to live Postgres and read back through a **second
connection**, checking the one property replay depends on.

| | |
|---|---|
| store | `trajectories`, `trajectory_steps`, `trajectory_tool_calls`, `trajectory_retrievals` in `faultline-postgres-1` |
| envelope | `logql_query`, 2010 bytes, from `docs/evidence/t2.6-tools-smoke/envelopes.txt` |
| result | **byte identity: PASS** |

## Files

- **`roundtrip.txt`** — the run, unedited.

## The property under test

ADR-0020 §3: *reconstructing what the model saw means storing the rendered text, not the object
it was rendered from.* A replay that re-renders from a typed result is replaying a different
prompt, and the difference does not show up in a diff of the two objects — only in the text.

So the envelope is stored as text and read back without normalisation, and this asserts it:

```
BYTE IDENTITY: PASS
  len  written 2010  read 2010
  sha256 written 17be986c80ca0236bc77752eb8ef1999ad917d7c20abb5bbc99d59ae75fa8cbc
  sha256 read    17be986c80ca0236bc77752eb8ef1999ad917d7c20abb5bbc99d59ae75fa8cbc
```

The closing delimiter survived intact — `</tool_result:tr_cc701817e51a>` — which is the part
that matters most. It carries the per-call random id that stops a log line closing a frame it
cannot name (ADR-0019 §2). A store that trimmed, re-encoded or re-rendered would break exactly
that, and a replayed prompt would still *look* right.

**This envelope contains no control characters.** The `logql_query` capture happened to be
clean. The stronger case — `cart-bad-image-tag`'s log capture carries five ANSI escapes — is
covered in `tests/test_agents_runtime.py` rather than here, and the schema's `TEXT` column is
what makes both survive.

## What else came back

```
read back 3 steps, model=claude-opus-5, role_models={'scribe': 'claude-haiku-4-5'}
retrieval: exclude_origin='scenario:cart-redis-misconfig' k=3 returned=[...]
steps by kind: ['message', 'tool_call', 'retrieval']
```

Three things worth naming.

**The effective role map survived, not just the default.** The trajectory was written with a
`scribe` override and read back with it. A published figure reports the map (ADR-0020 §1), and a
map that did not persist would leave the figure describing an experiment nobody ran.

**`exclude_origin` is a column and it round-trips.** This is where T4.1b reads ADR-0008's
assertion — the harness sets it on every scored run and asserts the filter fired, and a run
where it did not is marked invalid rather than annotated. It is now a value in a table rather
than a log line to grep.

**The inter-agent message is a step.** The planner's dispatch to the log specialist is in the
record, so scoring the synthesizer later can see what it was given (ADR-0020 §3).

## What this smoke did not exercise

- **Any model call.** `AgentSettings` was read (`model=claude-opus-5`, `judge=(unset)`) and no
  completion was requested. The optional `faultline[agents]` extra is not installed here.
- **A real investigation.** The trajectory is synthetic — three steps assembled by hand. The
  roles that would produce one do not exist yet; only triage is built.
- **Replay.** Nothing consumed the trajectory. T5.3 owns that, and this establishes the property
  replay needs rather than replay itself.
- **Scale.** One envelope. ADR-0020 asked whether envelopes should be content-addressed to avoid
  storing the same 500-line capture across repeats of one scenario; they are stored inline per
  `result_id`, with a `sha256` column so the question can be answered from data later without a
  migration.

## Reproducing

The script is in the commit that added this directory. It writes with one connection and reads
with another, deliberately — a round trip through one open session can be satisfied by a cache
rather than by the database.
