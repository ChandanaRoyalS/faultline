# Pre-registration - Q128's build: the DeathStarBench snapshots loaded by application

**Written before any code is changed. Nothing here is a result.** Q128 was queued by T7.2
topology item 4, whose two runs captured each DeathStarBench application's graph under SREGym:

- [Hotel Reservation's RESULT](../attempts/T7.2-graph4-hotel/RESULT.md);
- [Social Network's RESULT](../attempts/T7.2-graph4-social/RESULT.md).

Q125's registry loads an application's snapshot by name, but every entry must be read in one of
Faultline's worlds. These two belong to no world.

**The question.** Can `FAULTLINE_CONTEXT_APPLICATION` load each DeathStarBench snapshot, with a
catalog that says what each absent service is, while nothing else moves?

## Read before registration

- **The snapshots of record**, both SREGym's `/api/dependencies` replies, unmodified:

  | application | file | cross-service edges | self-edges | services in the graph |
  |---|---|---|---|---|
  | Hotel Reservation | `g4-hotel-deps-5m.json` (a 5-minute window, the store's whole reach) | 7 | 0 | 8 |
  | Social Network | `g4-social-deps-30m.json` | 8 | 0 | 6 |

- **Artifact edges: none.** The load generator (wrk2) emits no spans, so no edge describes how the
  world is run. Self-edges stay dropped by the loader's rule, though Jaeger v1 counts none.
- **Names.** Every name is the span's `service.name`, used as it is.
  - **Social Network's entry point is named `nginx-web-server` in spans, while its deployment is
    `nginx-thrift`.** The catalog uses the span name, as the graph does.
  - Nothing in Faultline addresses these applications' containers today, so no container map is
    needed. The graph's canonical form is the identity.
- **The absent services**, each from what the captures recorded:

  | application | service(s) | presence | evidence |
  |---|---|---|---|
  | Hotel Reservation | `mongodb-geo`, `mongodb-profile`, `mongodb-rate`, `mongodb-recommendation`, `mongodb-reservation`, `mongodb-user`, `memcached-profile`, `memcached-rate`, `memcached-reserve` | `INFRASTRUCTURE` | deployments in the capture's pod list; no span of their own in Jaeger's service list. **Their callers' client spans were not read**, unlike v2's datastores in Q122's probe |
  | Hotel Reservation | `consul` | `INFRASTRUCTURE` | the service registry the Go services register with (Addendum 1's reason Consul was not restarted); no span of its own |
  | Social Network | `text-service`, `unique-id-service`, `user-service`, `media-service`, `url-shorten-service`, `user-mention-service` | `UNLINKED` | Jaeger listed each (`g4-social-hold.txt`), and none appears in any edge of any lookback |
  | Social Network | `media-frontend` | `UNEXERCISED` | no log line after its restart (`g4-social-mediafrontend.txt`); not in Jaeger's list |
  | Social Network | the 13 datastores: `home-timeline-redis`, `social-graph-redis`, `user-timeline-redis`; `media-mongodb`, `post-storage-mongodb`, `social-graph-mongodb`, `url-shorten-mongodb`, `user-mongodb`, `user-timeline-mongodb`; `media-memcached`, `post-storage-memcached`, `url-shorten-memcached`, `user-memcached` | `INFRASTRUCTURE` | deployments in the capture's pod list; no span of their own. Their callers' client spans were not read |

  Each application's own Jaeger is telemetry and stays out of the catalog, as on v1 and v2.
- **The hop radius on these graphs**, measured by the same method as `ContextSettings.hop_radius`'s
  docstring:

  | graph | nodes | pairs | ≤ 1 | ≤ 2 | ≤ 3 |
  |---|---|---|---|---|---|
  | Hotel Reservation | 8 | 28 | 25 % | **71 %** | 100 % |
  | Social Network | 6 | 15 | 53 % | **93 %** | 100 % |

  On Social Network, radius 2 declines 7 % of pairs, so it is close to no filter. **Noticed, not
  changed**: whether the radius should differ per application is for scoping step 6. The
  docstring gains these rows.
- **No digest covers the graph.** At `8db2c18`: `cap:91279a09` and
  `faultline/0.0.1+prompts:9ce16b66bbcc`.

## The build

1. **`context/graph.py`**:
   - **`Application.world` may be `None`**, meaning names of no world, read as they are.
   - Two entries join `APPLICATIONS`: `sregym-hotel-reservation` → `g4-hotel-deps-5m.json` and
     `sregym-social-network` → `g4-social-deps-30m.json`, both with no world.
   - **`_resolve` asks no world of them**: the process world is not compared, because their names
     cannot clash with an injector that never addresses them.
   - `from_snapshot` reads them with the identity map, no artifact edges and no edge kinds, so
     every edge is `UNMEASURED`.
   - **The graph records `world=None`**, and canonicalises as the identity.
2. **`context/catalog.py`**:
   - `KNOWN_ABSENT_BY_APPLICATION`, holding the two tables above, each reason naming its evidence
     and what was not read;
   - the catalog uses its graph's application's table when it has one, and its world's otherwise,
     so astronomy-shop under SREGym keeps v2's.
3. **`context/settings.py`**: `hop_radius`'s docstring gains the two rows.
4. **`Dockerfile`** ships both files, and **`test_packaging`**'s `REPO_DATA` names them.
5. **Tests** (`test_context`):
   - each application loads its edges and nodes, all `UNMEASURED`;
   - each catalog's presences;
   - a blast radius each:
     - `geo` → `search` (1), `frontend` (2);
     - `post-storage-service` → `home-timeline-service`, `user-timeline-service` (1), then
       `nginx-web-server`, `compose-post-service` (2);
   - loading is the same in a v1 process and a v2 process;
   - an unknown application still raises, and naming the known ones lists all three.
6. **The records**: Q128 struck, `docs/PLAN.md`, the design note, and
   `evals/attempts/Q128-dsb-graphs/RESULT.md`.

**Not changed**: any prompt, contract or tool; the hop radius; `knowledge/`. There is no
services directory for these applications: it is a document, and none is asked for.

## Predictions, stated now

- **Hotel Reservation**: 7 edges, 8 nodes, a catalog of 18 entries (8 present, 10 absent).
  `blast_radius(["geo"], 2)` is `search` (1), then `frontend` (2), as also affected.
- **Social Network**: 8 edges, 6 nodes, a catalog of 26 entries (6 present, 6 `UNLINKED`, 1
  `UNEXERCISED`, 13 `INFRASTRUCTURE`). `blast_radius(["post-storage-service"], 2)` is:
  - `home-timeline-service` and `user-timeline-service` (1);
  - then `nginx-web-server` and `compose-post-service` (2), all also affected.
- **The same in a v1 and a v2 process.**
- **Unset, or set to `sregym-astronomy-shop`, nothing moves**, and every existing test passes
  unmodified.
- **Both stamps hold.**
- `make check` passes.

## Acceptance

The code above passes `make check`, and the RESULT reads each prediction, held or not. Then
scoping step 6 can name a snapshot for every application T7.2 runs.
