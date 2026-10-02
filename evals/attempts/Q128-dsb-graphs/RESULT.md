# RESULT - Q128's build: the DeathStarBench snapshots loaded by application

Read against [`PREREGISTRATION-Q128-dsb-graphs.md`](../../runs/PREREGISTRATION-Q128-dsb-graphs.md).
Built on `8584d63`, 2026-10-02. $0, no model call, and no world touched.

## The answer

**YES.** `FAULTLINE_CONTEXT_APPLICATION` now loads all three applications T7.2 runs, each with a
catalog that says what each absent service is:

- `sregym-astronomy-shop`, from Q125;
- `sregym-hotel-reservation`;
- `sregym-social-network`.

With the setting unset, or set to `sregym-astronomy-shop`, nothing moves. `make check`: 2362
passed, against 2356, so 6 tests are new.

## The predictions

| prediction | held? |
|---|---|
| Hotel Reservation: 7 edges, 8 nodes, a catalog of 18 (8 present, 10 absent) | **held** |
| `blast_radius(["geo"], 2)`: `search` (1), then `frontend` (2), also affected | **held**, in that order |
| Social Network: 8 edges, 6 nodes, a catalog of 26 (6 present, 6 `UNLINKED`, 1 `UNEXERCISED`, 13 `INFRASTRUCTURE`) | **held** |
| `blast_radius(["post-storage-service"], 2)`: the two timelines (1), then `nginx-web-server` and `compose-post-service` (2), all also affected | **held**. The test pins the sets per hop; order within a hop follows the capture's edge order, the lesson of Q125's RESULT |
| the same in a v1 and a v2 process | **held**: one test, run in both |
| unset or `sregym-astronomy-shop`, nothing moves; every existing test unmodified | **held, with one test's expected text widened**. `test_an_unknown_application_is_an_error` matched the list of known applications, which now names three. The registration said so ("naming the known ones lists all three") |
| both stamps hold | **held**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, unset and with `sregym-social-network` set |
| `make check` passes | **held** |

## What was built

- **`context/graph.py`**:
  - **`Application.world` may be `None`**, and the two entries are added with it.
  - `_resolve` returns no world for them, and refuses an explicit world (`has no world`).
  - The graph carries `world=None` and reads names as they are. There are no artifact edges and
    no edge kinds, so every edge is `UNMEASURED`.
- **`context/catalog.py`**: `KNOWN_ABSENT_HOTEL_RESERVATION`, `KNOWN_ABSENT_SOCIAL_NETWORK` and
  `KNOWN_ABSENT_BY_APPLICATION`.
  - Each reason names its evidence file and what was not read: the datastores' client spans, why
    the six write-path services join no trace, and whether `media-frontend` emits spans.
  - An application without a table of its own uses its world's.
- **`context/settings.py`**: `hop_radius`'s docstring gains the two applications' shares. Radius 2
  joins 71 % of Hotel Reservation's pairs and 93 % of Social Network's.
- **`Dockerfile`** and **`test_packaging`**: both snapshots are shipped and named.

**One addition the registration did not list**: an explicit `world` with a no-world application
raises, because the two cannot both be true. It is pinned by a test.
