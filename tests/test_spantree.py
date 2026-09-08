"""The span tree and the degrading-hop rule (T6.1).

The plan's trace analyst *"identifies the degrading hop in the request path."* This is the rule
that does it, and the rule is deterministic so a narrative can cite it and a reader can check it.
Two rules, in `faultline.tools.spantree`'s docstring: an error deep in the tree wins; otherwise
the span on the critical path that spent the time itself.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from faultline.tools import spantree
from faultline.tools.results import TraceSpan

T0 = datetime(2026, 9, 7, 15, 35, tzinfo=UTC)


def span(
    sid: str,
    parent: str,
    service: str,
    op: str,
    start_ms: float,
    dur_ms: float,
    error: bool = False,
    trace: str = "t1",
) -> TraceSpan:
    return TraceSpan(
        trace_id=trace,
        span_id=sid,
        parent_span_id=parent,
        service=service,
        operation=op,
        started_at=T0 + timedelta(milliseconds=start_ms),
        duration_ms=dur_ms,
        error=error,
        status="ERROR" if error else "OK",
    )


# The shape sweep 11's redis-cart-dependency-latency verdict described from a flat list and could
# not place: frontend -> cart GetCart -> two redis client spans of ~300ms each.
CART = [
    span("f", "", "frontend", "HTTP GET /cart", 0, 920),
    span("c", "f", "cartservice", "GetCart", 5, 610),
    span("r1", "c", "cartservice", "HGET", 6, 302),
    span("r2", "c", "cartservice", "HMSET", 310, 300),
    span("k", "f", "checkoutservice", "PlaceOrder", 620, 40),
]


def test_the_critical_path_and_self_time_name_the_slow_client_span() -> None:
    """No span errored, so rule 2: root -> longest child (GetCart, 610) -> its longest child
    (HGET, 302). Self-time: HGET 302 (a leaf), GetCart 610-602=8, root 920-650=270. HGET wins, and
    the hop is `cartservice/GetCart -> cartservice/HGET` - the closest an instrumented world can
    point at redis-cart."""
    (tree,) = spantree.build(CART)
    hop = spantree.degrading_hop(tree)

    assert hop is not None
    assert (hop.caller, hop.callee) == ("cartservice/GetCart", "cartservice/HGET")
    assert hop.error is False
    assert round(hop.share, 2) == round(302 / 920, 2)


def test_an_error_deep_in_the_tree_beats_a_slower_span_without_one() -> None:
    """Rule 1 over rule 2: the erroring span is where the failure originated, whatever the
    durations say. The shipping-quote shape: checkout's GetQuote client span errors fast."""
    spans = [
        span("f", "", "frontend", "POST /checkout", 0, 16),
        span("k", "f", "checkoutservice", "PlaceOrder", 1, 14),
        span("q", "k", "checkoutservice", "ShippingService/GetQuote", 2, 2, error=True),
        span("p", "k", "checkoutservice", "prepare", 4, 9),
    ]
    (tree,) = spantree.build(spans)
    hop = spantree.degrading_hop(tree)

    assert hop is not None and hop.error is True
    assert hop.callee == "checkoutservice/ShippingService/GetQuote"
    assert hop.caller == "checkoutservice/PlaceOrder"


def test_the_deepest_error_is_chosen_when_errors_propagate_upward() -> None:
    """Errors mirror up through the callers (the product-catalog shape). The hop ends at the
    deepest one, because the ones above are its propagation."""
    spans = [
        span("f", "", "frontend", "GET /product", 0, 9, error=True),
        span("p", "f", "productcatalogservice", "GetProduct", 1, 7, error=True),
        span("g", "p", "productcatalogservice", "FeatureFlagService/GetFlag", 2, 1),
    ]
    (tree,) = spantree.build(spans)
    hop = spantree.degrading_hop(tree)

    assert hop is not None
    assert hop.callee == "productcatalogservice/GetProduct"
    assert hop.caller == "frontend/GET /product"


def test_one_span_is_not_a_path() -> None:
    (tree,) = spantree.build([span("f", "", "frontend", "GET /", 0, 5)])

    assert spantree.degrading_hop(tree) is None
    assert "degrading hop" not in "\n".join(spantree.render(tree))


def test_orphans_are_attached_and_counted_rather_than_dropped() -> None:
    """A truncated fetch or a dropped span leaves children whose parent is absent. Losing spans is
    the defect this module replaces, so they hang under the root and the header says how many."""
    spans = [
        span("f", "", "frontend", "GET /", 0, 50),
        span("x", "missing", "cartservice", "GetCart", 10, 20),
    ]
    (tree,) = spantree.build(spans)

    assert tree.orphans == 1
    assert tree.span_count == 2
    header = spantree.render(tree)[0]
    assert "2 spans, 1 unattached" in header


def test_render_carries_offset_depth_duration_self_time_and_status() -> None:
    """Everything a verdict said it could not see in the flat list, on every line."""
    (tree,) = spantree.build(CART)
    lines = spantree.render(tree)

    assert lines[0].startswith(
        "trace t1  root frontend/HTTP GET /cart  920.0ms  started 2026-09-07"
    )
    assert "  +0.0ms frontend/HTTP GET /cart 920.0ms [self 270.0ms]" in lines
    assert "    +5.0ms cartservice/GetCart 610.0ms [self 8.0ms]" in lines
    assert "      +6.0ms cartservice/HGET 302.0ms [self 302.0ms]" in lines
    assert lines[-1].startswith(
        "  degrading hop: cartservice/GetCart -> cartservice/HGET  302.0ms, 33%"
    )


def test_wide_and_deep_traces_are_elided_with_a_marker_not_silently() -> None:
    wide = [span("r", "", "frontend", "GET /", 0, 100)] + [
        span(f"c{i}", "r", "adservice", f"GetAds{i}", i, 100 - i) for i in range(20)
    ]
    (tree,) = spantree.build(wide)
    text = "\n".join(spantree.render(tree))
    assert "12 shorter sibling span(s) elided" in text
    assert "GetAds0" in text and "GetAds19" not in text, "longest first, shortest elided"

    chain = [span("s0", "", "svc", "op0", 0, 100)] + [
        span(f"s{i}", f"s{i - 1}", "svc", f"op{i}", i, 100 - i) for i in range(1, 10)
    ]
    (tree,) = spantree.build(chain)
    lines = spantree.render(tree)
    assert any("deeper span(s) elided" in line for line in lines)
    # Elision is a rendering budget, not a blind spot: the deepest span is not drawn, and the hop
    # rule still runs over the whole tree and finds it.
    assert not any("+9.0ms svc/op9" in line for line in lines)
    assert lines[-1].startswith("  degrading hop: svc/op8 -> svc/op9")


def test_two_traces_render_as_two_trees_oldest_first() -> None:
    spans = [
        span("b", "", "frontend", "GET /b", 1000, 5, trace="t2"),
        span("a", "", "frontend", "GET /a", 0, 5, trace="t1"),
    ]
    trees = spantree.build(spans)

    assert [t.trace_id for t in trees] == ["t1", "t2"]


def test_spans_recorded_without_ids_still_build_a_tree() -> None:
    """Every span recorded before T6.1 has no `span_id`. They are roots of their own, rendered,
    and the hop rule runs over what it has rather than raising on an empty tree."""
    legacy = TraceSpan(
        trace_id="t", service="s", operation="op", started_at=T0, duration_ms=1.0, error=False
    )
    (tree,) = spantree.build([legacy, legacy])

    assert tree.span_count == 2
    assert spantree.render(tree)[0].startswith("trace t  root s/op")
