---
id: world-blast-radius-traversal
title: How a blast radius is walked, and what the walk does not claim
origin: authored
applies_to: [any]
signals: []
actions: []
---

The radius is a traversal of the measured dependency graph, computed rather than asked. The rules
are exact, they are directed, and two of them have been written down backwards before.

## The four rules

- **Upstream, transitive, to `radius` hops** - callee to caller. Failure propagates this way and a
  caller of an affected caller is affected, so it is followed to the full hop bound. These are
  `also_affected`.
- **Downstream, one step, and only from the seeds** - caller to callee, naming where an error
  could have come from. **It does not compose**: the callee of a *candidate* is a candidate for a
  fault nobody has evidence of. These are `candidate_cause`.
- **`async` is not crossed in either direction.** A producer keeps completing work while its
  consumer is dead, so neither end tells you about the other.
- **`unmeasured` is crossed**, and every crossing is counted and reported alongside the result. It
  is included and flagged, never silently promoted to `sync`.

## Direction is the whole point

ADR-0017's addendum defines `sync` as *a callee failure was observed to propagate to the caller*,
which is a **directed** statement. It licenses "this callee failed, so its caller is affected". It
does not license the reverse, and **treating the graph as undirected reads the measurement
backwards and inflates the result** - from one leaf's failure it would reach a service that merely
shares a caller with it and has nothing to do with it.

## The order is part of the contract, not an implementation detail

Upstream first in breadth-first order, then the downstream step, with each service claimed by the
first crossing that reaches it - so a service that is both upstream and downstream of the incident
comes out `also_affected`, the stronger claim.

**Seed order is the caller's and is preserved**, not collapsed into a set. That was not a
stylistic choice: an equivalence probe across all 91 seed sets found twelve that differed on
exactly this field.

**The seeds themselves are not in the result.** The caller supplied them and knows more about them
than the graph does.

## Two traversals, one radius, different rules

Correlation and blast radius both walk this graph at the same hop radius and they walk it
differently: correlation is **undirected and ignores edge kinds**, blast radius is **directed and
honours them**. The radius value is passed into triage rather than chosen there, because
correlation and blast radius disagreeing about how far apart two services are would make an
incident and its radius describe different graphs.

## The hop radius has weaker evidence than it looks

The figure behind 2 hops is a coverage measurement over the 13 real nodes and all 78 unordered
pairs: 1 hop covers 19%, **2 hops 72%**, 3 hops 97%. That measurement is **undirected**, and the
traversal above is not. **The undirected figure is an upper bound on directed coverage, not an
estimate of it**, and the directed number has never been computed. ADR-0017's addendum records
this rather than leaving the earlier figure to be read as though it still applied.

## What the result is not

**A set with entry times, not a ranked list.** Services reached across an edge have no entry time,
and that is not a gap to be filled - a service reached across an edge never alerted. The
`start_from` field is the earliest alerting service the graph can reason about and is **not a
culprit claim**.

Services the graph cannot see - `uninstrumented`, `artifact_only`, `infrastructure` - stay in the
output carrying their provenance, because **a service the graph cannot see is not a service that
was unaffected.**

## Where it is recomputed

The executor does not trust a stored scope: it recomputes the radius from the incident's own
episodes and adds the alerting services themselves, and it checks that scope **before** it checks
single use and before it checks the catalog. An action plane scoped to the alerting services alone
would refuse the correct remediation for any fault whose own service is silent.
