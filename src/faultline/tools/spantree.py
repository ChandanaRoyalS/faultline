"""The span tree, and the hop that degrades it (T6.1).

The execution plan's T6.1 names two tools: *"trace-search and span-tree summarizer"*, and a
specialist that *"identifies the degrading hop in the request path."* Until this module the trace
tool flattened every trace into a list and printed neither a span's start time nor its parent, and
three sweep-11 verdicts said exactly what that cost: *"traces carried no timestamps or status codes
and were truncated at 200 spans, so the slow spans cannot be pinned to the window or tied to
specific errored requests."* The evidence was in the traces; the shape hid it.

**Deterministic, and no model call.** A summariser is a rule, stated here so a narrative can cite
it and a reader can check it:

0. **If an erroring span gave up on a call that was still running, the degrading hop ends at
   the deepest span still waiting** (added under Q94, T7.1). Precisely: a span below an erroring
   one that had started before the erroring span ended, did not itself error, and ended at least
   `HANG_MARGIN_MS` after it. That is a timeout: the caller's deadline fired and turned into the
   trace's only error, while the call it abandoned went on waiting. On
   `v2-product-catalog-freeze`'s recording (2026-09-24) rule 1 named the proxy's 15 s timeout
   (`load-generator/GET -> frontend-proxy/ingress`) while frontend's request below it stayed open
   531.8 s, until the catalog resumed. The error was the edge of the hang, not its origin. The
   deepest still-waiting span is the call nearest the thing that stopped answering.
1. **If any span in the trace carries an error status, the degrading hop ends at the deepest
   erroring span** (ties broken by duration). An error deep in the tree is where the failure
   originated; the errors above it are its propagation.
2. **Otherwise, follow the critical path** - from the root, always into the child with the
   longest duration - and the degrading hop ends at the span on that path with the **largest
   self-time** (its duration less its children's). That is the span that spent the time itself
   rather than waiting on something below it.

The hop is `caller → callee`, both as `service/operation`, with the callee's share of the trace's
wall time. When the culprit is a datastore the world does not instrument - `redis-cart`, `kafka` -
the callee is the *client* span inside the instrumented service (`cartservice/HGET`), which is
the closest an instrumented world can point, and the reason ADR-0017's Addendum 3 put those
datastores in the catalog anyway.

**What this does not do.** It does not decide the culprit service, rank hypotheses, or read
anything but the spans it is given. Every number it prints is a subtraction or a division over
recorded durations, so two runs over the same trace print the same thing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from faultline.tools.results import TraceSpan

MAX_DEPTH = 6
"""v1's depth. Deeper than this, the tree is elided with a marker. Six covers loadgenerator →
frontend → checkout → cart → redis client with a level to spare; deeper traces are the exception
there. **It is v1's number and only v1's** (Q94): see `MAX_DEPTH_BY_WORLD`."""

V2_MAX_DEPTH = 16
"""v2's deepest span measured on the running world, plus one level to spare (Q94).

Measured 2026-09-24 on the healthy v2 world, over 30 minutes and 40 traces per service through
`trace_query` itself: the deepest span was at **15**, `flagd/resolveBoolean`. That is a feature-
flag evaluation at the bottom of a checkout request, which passes Envoy's two spans, Next.js's two,
checkout, its callees, and their flag checks. frontend, checkout, cart, product-catalog, shipping,
payment, currency, quote and email all reached 15; recommendation 12 (`product-catalog/
sql.conn.query`); ad 9. The freeze's trace alone had suggested about 9, because it stops at the
frozen catalog, so the figure was measured rather than read off it. Rendering deeper costs lines,
not spans: `MAX_CHILDREN` and the tool's span budget still bound the output."""

MAX_DEPTH_BY_WORLD: dict[str, int] = {"v1": MAX_DEPTH, "v2": V2_MAX_DEPTH}
"""Rendering depth per world (Q94, T7.1). v2 routes every request through Envoy (`ingress`,
`router frontend egress`) and the Next.js frontend adds its route spans (`GET /api/...`,
`executing api route`). On `v2-product-catalog-freeze`'s recording the span that names the frozen
catalog, frontend's call into it, sat at depth 7 and was elided at v1's 6. v2's figure is the
deepest span measured on the running world plus one level to spare, the same margin v1's six was
given. `V2_MAX_DEPTH` carries the measurement."""


def max_depth_for(world: str) -> int:
    """The rendering depth for `world`, v1's for any world this table does not name."""
    return MAX_DEPTH_BY_WORLD.get(world, MAX_DEPTH)


HANG_MARGIN_MS = 1000.0
"""How far past its erroring ancestor a span must run to count as still waiting (rule 0). Clock
skew between services and in-process work after a deadline are milliseconds. The hangs this rule
exists for last minutes (531.8 s on the freeze). A second separates the two with room on both
sides, and it is stated rather than fitted: no recorded trace sits between the two."""

STATUS_MESSAGE_MAX = 200
"""Characters of an ERROR span's status message rendered on its line. The message is the one
thing a span carries that a metric does not (Q94). R1's `Product Catalog Fail Feature Flag
Enabled` is 41 characters. The cap bounds what a service can write into the agent's context."""

MAX_CHILDREN = 8
"""Children rendered per span, longest first. The rest are counted, not printed."""


@dataclass
class Node:
    span: TraceSpan
    children: list[Node] = field(default_factory=list)
    depth: int = 0

    @property
    def self_ms(self) -> float:
        """Duration not accounted for by children - the time this span spent itself."""
        return max(0.0, self.span.duration_ms - sum(c.span.duration_ms for c in self.children))


@dataclass(frozen=True)
class Hop:
    caller: str
    """`service/operation` of the span above the degrading one; the root's own name when it is."""

    callee: str
    """`service/operation` of the degrading span."""

    duration_ms: float
    share: float
    """The callee's duration as a fraction of the trace's root duration, 0..1."""

    error: bool
    """Whether rule 1 (an error status) chose it, or rule 2 (self-time on the critical path)."""

    gave_up: str = ""
    """Rule 0 only: `service/operation` of the erroring span that stopped waiting, and how long
    the chosen span outlived it. Empty when rule 1 or 2 chose the hop."""

    outlived_ms: float = 0.0

    def label(self) -> str:
        if self.gave_up:
            why = f"still waiting {self.outlived_ms / 1000:.1f}s after {self.gave_up} gave up"
        else:
            why = "error" if self.error else "self-time"
        return (
            f"{self.caller} -> {self.callee}  {self.duration_ms:.1f}ms, "
            f"{self.share:.0%} of the trace ({why})"
        )


@dataclass
class Tree:
    trace_id: str
    root: Node
    span_count: int
    orphans: int
    """Spans whose parent is not in the trace as fetched. Attached under the root so they are
    rendered rather than dropped, and counted so a reader knows the tree is not complete."""


def build(spans: list[TraceSpan]) -> list[Tree]:
    """One tree per `trace_id`, oldest root first.

    A span whose parent is absent from the trace is an orphan - a truncated fetch, a dropped span,
    or a root whose parent lived in another process - and it is attached under the root rather
    than lost, because losing spans is the defect this module replaces.
    """
    by_trace: dict[str, list[TraceSpan]] = {}
    for span in spans:
        by_trace.setdefault(span.trace_id, []).append(span)

    trees: list[Tree] = []
    for trace_id, members in by_trace.items():
        # A span recorded without an id (every span before T6.1, and any store that omits one)
        # gets a synthetic id so it is still a node: it can be nobody's parent, and it is a root
        # unless it names one.
        nodes = {(s.span_id or f"_anonymous_{i}"): Node(s) for i, s in enumerate(members)}
        roots = [n for n in nodes.values() if not n.span.parent_span_id]
        orphans = 0
        for node in nodes.values():
            parent = node.span.parent_span_id
            if not parent:
                continue
            if parent in nodes:
                nodes[parent].children.append(node)
            else:
                orphans += 1
        if not roots:
            # Every span claims a parent; the earliest-starting one stands in as the root.
            roots = [min(nodes.values(), key=lambda n: n.span.started_at)]
        root = min(roots, key=lambda n: n.span.started_at)
        for node in nodes.values():
            if node is not root and node.span.parent_span_id not in nodes and node not in roots:
                root.children.append(node)
        for extra in roots:
            if extra is not root:
                root.children.append(extra)
        orphans += _break_cycles(root, list(nodes.values()))
        _assign_depth(root, 0)
        for node in nodes.values():
            node.children.sort(key=lambda c: c.span.duration_ms, reverse=True)
        trees.append(Tree(trace_id=trace_id, root=root, span_count=len(members), orphans=orphans))
    trees.sort(key=lambda t: t.root.span.started_at)
    return trees


def _break_cycles(root: Node, nodes: list[Node]) -> int:
    """Make the children graph a tree: drop every edge into a node already reached, and hang
    any node the root cannot reach under the root. Returns how many were hung that way.

    A span that names itself as parent, or two spans naming each other (a store that returns a
    span twice under one id, a producer/consumer pair whose ids collide), gives `build` a cycle.
    `_assign_depth` and `_walk` already stepped around cycles with a seen-set; `render` did not,
    and on R5 (2026-09-24, kafka disk fill) `trace_query checkout --errors` died of
    `RecursionError` in `emit` on a real trace. The agent's tool must never raise on the store's
    data: a cycle is a malformed trace and is rendered as one, its extra edges cut and its members
    kept, not a crash. Which edge is cut follows children order (longest first), which is
    deterministic for one fetch.
    """
    seen: set[int] = set()

    def prune_from(start: Node) -> None:
        seen.add(id(start))
        stack = [start]
        while stack:
            current = stack.pop()
            kept: list[Node] = []
            for child in current.children:
                if id(child) in seen:
                    continue
                seen.add(id(child))
                kept.append(child)
                stack.append(child)
            current.children = kept

    prune_from(root)
    rescued = 0
    for node in nodes:
        if id(node) not in seen:
            # Reachable only through a cycle the root never enters (two spans naming each other
            # and nothing else): it hangs under the root like any other unattached span, with its
            # own subtree pruned the same way so the cycle does not come along.
            prune_from(node)
            root.children.append(node)
            rescued += 1
    return rescued


def _assign_depth(node: Node, depth: int) -> None:
    stack = [(node, depth)]
    seen: set[int] = set()
    while stack:
        current, d = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        current.depth = d
        stack.extend((child, d + 1) for child in current.children)


def _walk(node: Node) -> list[Node]:
    out: list[Node] = []
    stack = [node]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        out.append(current)
        stack.extend(current.children)
    return out


def _name(node: Node) -> str:
    return f"{node.span.service}/{node.span.operation}"


def _end_ms(node: Node) -> float:
    return node.span.started_at.timestamp() * 1000.0 + node.span.duration_ms


def _start_ms(node: Node) -> float:
    return node.span.started_at.timestamp() * 1000.0


def hang_hop(tree: Tree) -> Hop | None:
    """Rule 0 alone: the deepest span still waiting when an erroring ancestor gave up, or `None`.

    Exposed apart from `degrading_hop` so a replay over recorded traces can show exactly which
    hops the rule moved and which it left to rules 1 and 2."""
    nodes = _walk(tree.root)
    parents = {id(c): n for n in nodes for c in n.children}
    total = tree.root.span.duration_ms or 1.0
    best: tuple[Node, Node] | None = None
    for gave_up in (n for n in nodes if n.span.error):
        deadline = _end_ms(gave_up)
        for waiting in _walk(gave_up)[1:]:
            if waiting.span.error:
                continue
            if _start_ms(waiting) >= deadline or _end_ms(waiting) < deadline + HANG_MARGIN_MS:
                continue
            # Deepest waiting span first; of the erroring ancestors that abandoned it, the
            # nearest, since the ones above it are its propagation (rule 1's reading of errors).
            key = (waiting.depth, waiting.span.duration_ms, gave_up.depth)
            if best is None or key > (best[1].depth, best[1].span.duration_ms, best[0].depth):
                best = (gave_up, waiting)
    if best is None:
        return None
    gave_up, chosen = best
    parent = parents.get(id(chosen))
    return Hop(
        caller=_name(parent) if parent is not None else _name(chosen),
        callee=_name(chosen),
        duration_ms=chosen.span.duration_ms,
        share=min(1.0, chosen.span.duration_ms / total),
        error=False,
        gave_up=_name(gave_up),
        outlived_ms=_end_ms(chosen) - _end_ms(gave_up),
    )


def degrading_hop(tree: Tree) -> Hop | None:
    """Rules 0, 1 and 2 from the module docstring, in that order. `None` only for a single-span
    trace with nothing to compare against - one span is not a path."""
    hang = hang_hop(tree)
    if hang is not None:
        return hang
    return error_or_self_time_hop(tree)


def error_or_self_time_hop(tree: Tree) -> Hop | None:
    """Rules 1 and 2 - the rule as it stood before Q94, kept callable so the replay can compare."""
    nodes = _walk(tree.root)
    parents = {id(c): n for n in nodes for c in n.children}
    total = tree.root.span.duration_ms or 1.0

    erroring = [n for n in nodes if n.span.error]
    if erroring:
        chosen = max(erroring, key=lambda n: (n.depth, n.span.duration_ms))
        by_error = True
    else:
        if len(nodes) == 1:
            return None
        path = [tree.root]
        while path[-1].children:
            path.append(path[-1].children[0])  # children are sorted longest first
        chosen = max(path, key=lambda n: n.self_ms)
        by_error = False

    parent = parents.get(id(chosen))
    caller = _name(parent) if parent is not None else _name(chosen)
    return Hop(
        caller=caller,
        callee=_name(chosen),
        duration_ms=chosen.span.duration_ms,
        share=min(1.0, chosen.span.duration_ms / total),
        error=by_error,
    )


def render(tree: Tree, max_depth: int = MAX_DEPTH) -> list[str]:
    """The tree as indented lines: offset from the root's start, name, duration, self-time,
    status and, on an ERROR span, its status message - then the hop. Everything a verdict said it
    could not see. `max_depth` is the world's (`max_depth_for`)."""
    root_start = tree.root.span.started_at
    lines = [
        f"trace {tree.trace_id[:16]}  root {_name(tree.root)}  "
        f"{tree.root.span.duration_ms:.1f}ms  started {root_start.isoformat()}  "
        f"{tree.span_count} spans" + (f", {tree.orphans} unattached" if tree.orphans else "")
    ]

    def emit(node: Node) -> None:
        if node.depth > max_depth:
            return
        offset = (node.span.started_at - root_start).total_seconds() * 1000.0
        flag = "  ERROR" if node.span.error else ""
        message = " ".join(node.span.status_message.split())[:STATUS_MESSAGE_MAX]
        if node.span.error and message:
            flag += f": {message}"
        indent = "  " * (node.depth + 1)
        lines.append(
            f"{indent}+{offset:.1f}ms {_name(node)} {node.span.duration_ms:.1f}ms "
            f"[self {node.self_ms:.1f}ms]{flag}"
        )
        if node.depth == max_depth and node.children:
            lines.append(f"{'  ' * (node.depth + 2)}... {len(node.children)} deeper span(s) elided")
            return
        shown = node.children[:MAX_CHILDREN]
        for child in shown:
            emit(child)
        hidden = len(node.children) - len(shown)
        if hidden > 0:
            lines.append(f"{'  ' * (node.depth + 2)}... {hidden} shorter sibling span(s) elided")

    emit(tree.root)
    hop = degrading_hop(tree)
    if hop is not None:
        lines.append(f"  degrading hop: {hop.label()}")
    return lines
