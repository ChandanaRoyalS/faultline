# ADR-0044: Faultline under SREGym - the adapter

- **Status:** accepted
- **Date:** 2026-10-03
- **Task:** T7.2 (the external benchmark run), the adapter build
- **Registered in:** [`PREREGISTRATION-T7.2-adapter.md`](../../evals/runs/PREREGISTRATION-T7.2-adapter.md),
  under the run's [`PREREGISTRATION-T7.2-run.md`](../../evals/runs/PREREGISTRATION-T7.2-run.md)
- **Relates to:** [ADR-0004](0004-benchmark-target.md) (the target and its four corrections),
  [ADR-0019](0019-tool-layer.md) (the tool layer and its leak boundary),
  [ADR-0017](0017-context-layer-graph-and-dependency-policy.md) (topology from a snapshot)

## Context

The execution plan's T7.2 asks for *"a thin adapter presenting Faultline's agent to an external
benchmark … adapter kept thin so the agent under test is the real one."* ADR-0004 found SREGym's
tools to be MCP over SSE, its change surface absent and its grading two-staged. The scoping steps
since added three constraints the adapter has to meet:

- **the agent runs in SREGym's container**: root and hardened, on an internal network whose only
  exit is an egress proxy (`--internet-access filtered`, frozen by the run's registration);
- **SREGym hands the agent no alert**, and a Faultline incident is alerts and nothing else;
- **the verdict becomes prose for an LLM judge**, and how is a free parameter that moves the
  number (the harness read, second addendum).

## Decision

**1. The tools are `McpToolSet`, a subclass of `Tools` over SREGym's MCP servers.** It overrides
the backend reads and nothing around them.

- The window policy, breakers, baseline windows, summaries, change points and the span tree stay
  the code the agent always ran.
- The metric baseline's body is copied, and a test holds it equal to `Tools`'.
- What SREGym's servers cannot do is stated in the result, never hidden:
  - instant metric queries, read as `@`-pinned subqueries;
  - 100 log lines from a window ending now, which is `truncated` when hit;
  - 20 traces, likewise.

**Not the backends directly.** Port-forwarding to SREGym's Prometheus, Loki and Jaeger would
give Faultline richer reads than the servers every other agent's observability goes through.
That is a different benchmark condition, and it is unregistered.

**2. Change history is Kubernetes' own record**, through the `changes` seam `Tools` already had
(the owner's decision of 2026-10-02).

- Fixed, read-only kubectl commands: revisions, pod-template diffs, ConfigMap and Secret
  times, and events. **As the pilot rewrote them** (adapter registration, Addendum 4, F2), each
  asks for named fields only, so that every answer fits SREGym's 10,000-character cut, and the
  owner's decision of 2026-10-03 adds Services, NetworkPolicies and claims, by name and time
  only.
- Secrets are read for their names and times only, never their values.
- **The leak guard** keeps annotations, labels, field managers and event reasons out of every
  record, and withholds any text that names the harness.

**3. The incident opens on standard health alarms.** The rules:

- kube-prometheus' pod and replica rules;
- Faultline's own three where the application has span metrics.

They are evaluated at the start, and once a minute for five minutes, with a front-door fallback
(the owner's decision). It is how Faultline is woken in production, by rules over metrics, with
the evaluator moved into the adapter because SREGym's Prometheus has no rules.

**4. The database is outside the box.** Postgres refuses to run as root, and the box is root with
no way to switch user. Stage 0 measured the alternative:

- a pgvector Postgres on the deployment's `docker0`;
- reached through SREGym's own proxy by a CONNECT tunnel;
- 50 round trips in 61 ms.

Each attempt recreates its database from a seeded template, so attempts cannot see each other.

**5. The agent is invoked as the CLI it is.** `faultline-investigate` gains one switch,
`FAULTLINE_TOOLS_BACKEND=sregym`, that builds `McpToolSet` instead of `Tools`. The adapter runs it
as a subprocess with the scored runs' budget, as `evalharness.run` does, rather than rebuilding
the engine beside it. Two assemblies of one agent are two agents.

**6. The rendering is frozen** as the run's registration states it, with no model call, and a
golden-text test holds it.

## Consequences

- **The stamps hold**: `cap:91279a09` and `faultline/0.0.1+prompts:9ce16b66bbcc`. No tool, prompt,
  contract or role changed, and `capability.tool_surface()` reads `Tools`, which is untouched.
- **What a SREGym score measures** is Faultline with its four modalities as SREGym serves them:
  - metrics and logs, coarser than its own world's;
  - traces only where the application sends them (Q127);
  - change history from Kubernetes' record, not a deploy log;
  - no general describe.

  The run's registration states all four beside the number.
- **The trace result still says `source: tempo`.** It is a contract literal, and changing it
  would move the prompt digest for a label the prompts never read. Recorded, not fixed.
- **Benchmark state never reaches the product**: a separate database, notifications off, and no
  corpus write that one attempt could read in the next.

- **Two of SREGym's properties are reported as unavailable, never as numbers** (adapter
  registration, Addendum 4): a service with no span-metric series, and Astronomy Shop's latency,
  whose histogram tops out at 0.005 ms. Faultline's own windows are left as they are, although
  SREGym's Prometheus holds minutes of history (the owner's decision of 2026-10-03).

**Revisit if** SREGym's MCP servers gain range queries or larger caps (the overrides would then
be giving up fidelity for nothing), or its agent container stops being root (Postgres could then
move inside).
