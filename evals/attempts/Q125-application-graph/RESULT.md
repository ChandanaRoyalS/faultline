# RESULT - Q125's build: the dependency snapshot loaded by application

Read against [`PREREGISTRATION-Q125-application-graph.md`](../../runs/PREREGISTRATION-Q125-application-graph.md).
Built on `60abdbb`, 2026-10-02. $0, no model call, and no world touched.

## The answer

**YES.** With `FAULTLINE_CONTEXT_APPLICATION=sregym-astronomy-shop` (and `FAULTLINE_TOOLS_WORLD=v2`),
Faultline loads SREGym's astronomy-shop snapshot. That is 20 edges over 15 services, the same graph
as v2's, under a catalog of the same 23 entries and presences. With the setting unset, every
existing test passes unmodified, and v1 and v2 load as before. `make check`: 2356 passed, against
2349 at `60abdbb`, so 7 tests are new.

## The predictions

| prediction | held? |
|---|---|
| the application's graph equals v2's: 20 edges, 15 nodes, the same `edge_set` | **held** |
| its catalog: the same 23 entries and presences | **held** |
| its blast radius from `checkout` is v2's, **in the same order** | **half held**. The same eight members, the same crossings and the same unmeasured edges, but the six candidate causes come in a different order (`payment, product-catalog, cart, email, shipping, currency` against v2's `product-catalog, currency, cart, email, payment, shipping`). The downstream step follows each capture's edge order, and the two captures list checkout's callees differently. The test pins the sets, and that the order differs |
| unset, nothing moves; every existing test unmodified; `make check` passes | **held** |
| both stamps stay, with and without the application | **held**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc` both ways |

**The order is part of `blast_radius`'s contract** (its docstring), because triage results are
scored against recorded bundles. Two graphs with the same edges can still give a different order,
then, if their files list the edges differently. **Nothing scored is affected**: no scored run
exists on v2 or on SREGym. Any future comparison of triage across the two applications has to
compare sets.

## What was built

- **`context/settings.py`**: `ContextSettings.application`. The `hop_radius` docstring gains v2's
  shares: 61 % of 105 pairs within 2 hops, so 39 % declined.
- **`context/graph.py`**:
  - `Application`, `APPLICATIONS` (`sregym-astronomy-shop` → `g3-deps-60m.json`, read in `v2`) and
    `current_application()`;
  - `_resolve`, with the two errors: an unknown name, and an application whose world is not the
    process's;
  - `from_snapshot(..., application=None)`;
  - the graph carries `application`.
- **`context/catalog.py`**: `from_snapshot(..., application=None)`, and the note beside
  `KNOWN_ABSENT_V2` saying what was checked on SREGym and what was not.
- **`Dockerfile`** and **`test_packaging`**: the snapshot is shipped and named.
- **`test_context`**: seven tests.

**An explicit `world` means "by world"**: the application setting is read only when neither is
passed. The registration did not say how the two combine, so this is stated here and pinned by a
test.
