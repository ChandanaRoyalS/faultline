"""Faultline presented to SREGym as an agent (T7.2, ADR-0044).

`docs/design/t7.2-scoping.md` step 2 extracted the `ToolSet` protocol so that the agent could read
a world through something other than `Tools`' HTTP backends. This package is that something for
SREGym, plus the few pieces SREGym needs and Faultline's own world never did:

- `mcp`: a minimal MCP-over-SSE client, standard library only, for SREGym's five servers;
- `toolset`: `McpToolSet`, the five tools over those servers. It subclasses `Tools`, so window
  discipline, breakers, summaries and span trees are the same code the agent always ran;
- `kube`: the change log over Kubernetes' own record, read-only, with a leak guard;
- `opening`: the incident opened on standard health alarms, since SREGym gives no alert;
- `render`: the verdict as the text SREGym's judge grades, frozen by registration;
- `tunnel`: a loopback port to the benchmark database through SREGym's egress proxy;
- `driver`: one attempt, end to end, invoking `faultline-investigate` as the CLI it is.

**Nothing here is a tool, a prompt, a contract or a role.** Registered in
`evals/runs/PREREGISTRATION-T7.2-adapter.md`; the stamps are checked against it.
"""
