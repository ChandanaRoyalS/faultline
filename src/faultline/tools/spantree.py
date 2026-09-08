"""The span tree, and the hop that degrades it (T6.1).

The execution plan's T6.1 names two tools: *"trace-search and span-tree summarizer"*, and a
specialist that *"identifies the degrading hop in the request path."* Until this module the trace
tool flattened every trace into a list and printed neither a span's start time nor its parent, and
three sweep-11 verdicts said exactly what that cost: *"traces carried no timestamps or status codes
and were truncated at 200 spans, so the slow spans cannot be pinned to the window or tied to
specific errored requests."* The evidence was in the traces; the shape hid it.

**Deterministic, and no model call.** A summariser is a rule, stated here so a narrative can cite
it and a reader can check it:

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
"""Deeper than this, the tree is elided with a marker. Six covers loadgenerator → frontend →
checkout → cart → redis client with a level to spare; deeper traces are the exception here."""

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

    def label(self) -> str:
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
        _assign_depth(root, 0)
        for node in nodes.values():
            node.children.sort(key=lambda c: c.span.duration_ms, reverse=True)
        trees.append(Tree(trace_id=trace_id, root=root, span_count=len(members), orphans=orphans))
    trees.sort(key=lambda t: t.root.span.started_at)
    return trees


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


def degrading_hop(tree: Tree) -> Hop | None:
    """Rules 1 and 2 from the module docstring. `None` only for a single-span trace with
    nothing to compare against - one span is not a path."""
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


def render(tree: Tree) -> list[str]:
    """The tree as indented lines: offset from the root's start, name, duration, self-time,
    status - then the hop. Everything a verdict said it could not see."""
    root_start = tree.root.span.started_at
    lines = [
        f"trace {tree.trace_id[:16]}  root {_name(tree.root)}  "
        f"{tree.root.span.duration_ms:.1f}ms  started {root_start.isoformat()}  "
        f"{tree.span_count} spans" + (f", {tree.orphans} unattached" if tree.orphans else "")
    ]

    def emit(node: Node) -> None:
        if node.depth > MAX_DEPTH:
            return
        offset = (node.span.started_at - root_start).total_seconds() * 1000.0
        flag = "  ERROR" if node.span.error else ""
        indent = "  " * (node.depth + 1)
        lines.append(
            f"{indent}+{offset:.1f}ms {_name(node)} {node.span.duration_ms:.1f}ms "
            f"[self {node.self_ms:.1f}ms]{flag}"
        )
        if node.depth == MAX_DEPTH and node.children:
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
