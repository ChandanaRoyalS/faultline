# Pre-registration - Q125's build: the dependency snapshot loaded by application

**Written before any code is changed. Nothing here is a result.** Q125 was opened by
[T7.2 topology item 3's RESULT](../attempts/T7.2-graph3/RESULT.md). Astronomy-shop under SREGym
read DIFFERENT from v2's snapshot of record. So, by the owner's decision of 2026-10-02, it has
its own snapshot (`docs/evidence/t7.2-topology/g3-deps-60m.json`), and loading by application is
built before any scored run.

**The question.** Can Faultline load SREGym's astronomy-shop snapshot when told it is running
against that application, while every run that names no application is exactly as before?

## Decided by the owner, 2026-10-02, before this registration

- **A new setting, `ContextSettings.application`** (`FAULTLINE_CONTEXT_APPLICATION`). Unset by
  default, and unset means: load by world, exactly as today. Its values come from a registry,
  whose first and only entry is **`sregym-astronomy-shop`**.
  - **Rejected**: a third value of `ToolSettings.world`. The world also picks the span-metric
    names and the container map, which mean nothing on Kubernetes, and a wrong value there fails
    as empty PromQL, not as an error.
- **The catalog's absent-service reasons are v2's, reused and checked against what item 3
  recorded on SREGym**, not measured there by another run.

## Read before registration

- **The two snapshots, loaded with v2's rules, are identical**: the same 20 edges over the same 15
  services (item 3's RESULT, checked by comparing `edge_set` and `nodes`).
  - Raw, SREGym's has 21 cross-service edges and no self-edges.
  - v2's has 22 cross-service edges and 16 self-edges.
  - The one raw difference, `load-generator → flagd`, is in `ARTIFACT_EDGES_V2`.
- **`KNOWN_ABSENT_V2` against SREGym's record.** SREGym's Jaeger listed 19 services in the clean
  capture (`g3-hold.txt`): the 15 nodes, `load-generator`, `accounting`, `image-provider`, and its
  own `jaeger-all-in-one`.

  | entry | v2's presence | what item 3 recorded on SREGym | consistent? |
  |---|---|---|---|
  | `load-generator` | `ARTIFACT_ONLY` | its only edge, to `frontend-proxy`, is an artifact edge | yes |
  | `accounting` | `UNLINKED` | listed (emits spans), no edge | yes |
  | `image-provider` | `UNLINKED` | listed (emits spans), no edge | yes |
  | `llm` | `UNINSTRUMENTED` | not listed (no spans). Whether it served requests was not read | yes, as far as read |
  | `flagd-ui` | `UNEXERCISED` | not listed. Whether anything reached it was not read | yes, as far as read |
  | `valkey-cart`, `postgresql`, `kafka` | `INFRASTRUCTURE` | not listed (no spans of their own). Their callers' client spans were **not** read | yes, as far as read |

  **What is not checked is said so in the code**, beside the table it reuses.
- **Where the world comes from.** The application's snapshot is in v2's names. If the process's
  `ToolSettings.world` is not `v2` while the application is set, the graph's names and the
  injector's would differ silently. That is the failure the rejected option had, so **the build
  makes it an error**.
- **No digest covers the graph** (Q122's read).
  - **At `f361363`**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`.
  - The new setting is in `ContextSettings`, which neither digest reads.
- **A docstring that is v1's alone.** `ContextSettings.hop_radius` quotes *"Over the 13 nodes and
  all 78 unordered pairs"*: radius 2 joins 72 % and declines 28 %, and its readers are told to
  quote the 28 %. On v2's loaded graph, and so on SREGym's, the figures differ:

  | graph | nodes | pairs | ≤ 1 hop | ≤ 2 hops | ≤ 3 hops | ≤ 4 hops |
  |---|---|---|---|---|---|---|
  | v1 | 13 | 78 | 19 % | 72 % | 97 % | 100 % |
  | v2 | 15 | 105 | 19 % | **61 %** | 90 % | 99 % (100 % at 5) |

  So radius 2 declines **39 %** of v2's pairs. The docstring gains the v2 row. The radius does not
  change: 2 is still the only value that is neither the emailservice-failing 1 nor the
  near-everything 3.

## The build

1. **`context/settings.py`**: `application: str | None = None`, with its docstring.
2. **`context/graph.py`**:
   - an `Application` record (name, snapshot path, the world whose names and rules it is read
     with);
   - `APPLICATIONS = {"sregym-astronomy-shop": ...}`, whose snapshot is `g3-deps-60m.json`, in
     place, read in `v2`;
   - `current_application()`;
   - `from_snapshot(path=None, world=None, application=None)`:
     - the application, if one is named or set, decides the snapshot and the world;
     - **a process world that differs from it raises `ValueError`**;
     - an unknown name raises `ValueError`, listing the known ones;
     - unset, nothing changes.
   - The graph carries `application`, `None` when loaded by world.
3. **`context/catalog.py`**:
   - `ServiceCatalog.from_snapshot(world=None, application=None)`;
   - the absent-service table still follows the graph's world, so the application reuses
     `KNOWN_ABSENT_V2`;
   - a note beside `KNOWN_ABSENT_V2` says what was checked on SREGym and what was not.
4. **`Dockerfile`** ships `g3-deps-60m.json`, and **`test_packaging`**'s `REPO_DATA` names it.
5. **Tests** (`test_context`):
   - the application loads 21 raw entries to 20 edges over 15 nodes;
   - its `edge_set` and `nodes` equal v2's;
   - the catalog gives the same 23 services and presences;
   - `blast_radius(["checkout"])` equals v2's;
   - a v1 process world with the application set raises;
   - an unknown application raises;
   - unset leaves v1 and v2 as they are.
6. **The records**: Q125 struck, `docs/PLAN.md`, the design note, and
   `evals/attempts/Q125-application-graph/RESULT.md`.

**Not changed**:

- `knowledge/services-v2.yaml`: a document whose `depends_on` is v2's measured edges, the same
  names;
- any prompt, contract or tool;
- the hop radius itself.

## Predictions, stated now

- **The application's graph equals v2's**: 20 edges, 15 nodes, the same `edge_set`. Its catalog
  has the same 23 entries with the same presences. Its blast radius from `checkout` is v2's, in
  the same order.
- **Unset, nothing moves.** Every existing test passes unmodified, and `make check` passes.
- **Both stamps stay**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`, with and
  without the application set.

## Acceptance

The build is done when the code above passes `make check`, and the RESULT reads each prediction,
held or not.

**Out of scope**:

- the DeathStarBench applications, whose entries join the registry as each graph is captured
  (the design note's item 4);
- Q124 and Q126 (owner's decisions pending);
- Q121's guard.
