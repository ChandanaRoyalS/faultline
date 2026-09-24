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


def test_a_cycle_in_the_spans_renders_as_a_tree_instead_of_recursing_forever() -> None:
    """R5 (2026-09-24): `trace_query checkout --errors` on a kafka disk fill died of RecursionError
    in `render` - a real trace whose spans formed a cycle. The tool must not raise on the store's
    data; the cycle's extra edges are cut, every span is kept, and the header counts the ones hung
    under the root."""
    spans = [
        span("f", "", "frontend", "GET /", 0, 50),
        span("a", "f", "checkout", "PlaceOrder", 5, 30),
        span("b", "c", "kafka", "publish", 10, 5),  # b's parent is c ...
        span("c", "b", "kafka", "consume", 12, 5),  # ... and c's parent is b
        span("s", "s", "cart", "GetCart", 20, 2),  # its own parent
    ]
    (tree,) = spantree.build(spans)

    lines = spantree.render(tree)  # must return
    joined = "\n".join(lines)
    assert tree.span_count == 5
    assert "5 spans" in lines[0] and "unattached" in lines[0]
    for name in ("PlaceOrder", "publish", "consume", "GetCart"):
        assert name in joined, f"{name} was lost"
    assert spantree.degrading_hop(tree) is not None


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


# --- Q94 (T7.1): depth per world, status messages, and rule 0 -----------------------------------

# The shape `trace_query frontend --errors` rendered over `v2-product-catalog-freeze`'s recording
# (2026-09-24 16:53): the proxy's 15 s deadline is the trace's only error, and below it frontend's
# request stays open until the catalog resumes, 531.8 s later. The client span into the catalog is
# the one v1's depth elided.
FREEZE = [
    span("root", "", "load-generator", "user_add_to_cart", 0, 15006.2),
    span("lg", "root", "load-generator", "GET", 0.3, 15002.3, error=True),
    span("px", "lg", "frontend-proxy", "ingress", 0.6, 15001.6, error=True),
    span("rt", "px", "frontend-proxy", "router frontend egress", 0.7, 15001.4),
    span("fe", "rt", "frontend", "GET", 1.0, 15001.3),
    span("api", "fe", "frontend", "GET /api/products/{productId}", 1.0, 531801.7),
    span("route", "api", "frontend", "executing api route (pages)", 1.0, 531801.3),
    span("grpc", "route", "frontend", "oteldemo.ProductCatalogService/GetProduct", 1.2, 531800.9),
]


def test_a_hang_under_a_timeout_names_the_call_still_waiting_not_the_timeout() -> None:
    """**Rule 0.** Rule 1 alone named `load-generator/GET -> frontend-proxy/ingress`, the edge
    where the deadline fired - true and no help. The deepest span still running when the proxy
    gave up is frontend's call into the frozen catalog, and that is the hop."""
    (tree,) = spantree.build(FREEZE)

    old = spantree.error_or_self_time_hop(tree)
    assert old is not None and old.callee == "frontend-proxy/ingress", "rules 1-2, as before"

    hop = spantree.degrading_hop(tree)
    assert hop is not None
    assert hop.callee == "frontend/oteldemo.ProductCatalogService/GetProduct"
    assert hop.caller == "frontend/executing api route (pages)"
    assert hop.gave_up == "frontend-proxy/ingress"
    assert hop.label().endswith("(still waiting 516.8s after frontend-proxy/ingress gave up)")
    assert hop.share == 1.0, "a span that outlives its root is 100% of the trace, capped"


def test_rule_0_leaves_ordinary_errors_to_rule_1() -> None:
    """Three shapes that must not read as hangs:

    - an erroring parent whose child finished inside it (the ordinary propagated error);
    - an async consumer that starts after the erroring producer ended, however long it runs;
    - a child that outlives its erroring parent by skew-sized milliseconds.
    """
    propagated = [
        span("f", "", "frontend", "GET /", 0, 50, error=True),
        span("c", "f", "checkout", "PlaceOrder", 2, 40, error=True),
        span("p", "c", "payment", "Charge", 3, 30),
    ]
    consumer = [
        span("c", "", "checkout", "PlaceOrder", 0, 20, error=True),
        span("k", "c", "checkout", "orders publish", 5, 4),
        span("a", "k", "accounting", "order-consumed", 30, 90000),
    ]
    skew = [
        span("px", "", "frontend-proxy", "ingress", 0, 15000, error=True),
        span("fe", "px", "frontend", "GET", 0.2, 15000.5),
    ]
    for spans in (propagated, consumer, skew):
        (tree,) = spantree.build(spans)
        assert spantree.hang_hop(tree) is None
        assert spantree.degrading_hop(tree) == spantree.error_or_self_time_hop(tree)


def test_an_erroring_descendant_is_not_a_span_still_waiting() -> None:
    """A deeper span that itself errored is rule 1's to name, not rule 0's."""
    spans = [
        span("px", "", "frontend-proxy", "ingress", 0, 15000, error=True),
        span("fe", "px", "frontend", "GET", 1, 60000, error=True),
    ]
    (tree,) = spantree.build(spans)
    assert spantree.hang_hop(tree) is None


def test_the_depth_is_the_worlds() -> None:
    """v1 renders exactly as before; v2 draws the freeze's culprit span that v1's six elided."""
    assert spantree.max_depth_for("v1") == spantree.MAX_DEPTH == 6
    assert spantree.max_depth_for("v2") == spantree.V2_MAX_DEPTH > spantree.MAX_DEPTH
    assert spantree.max_depth_for("some-future-world") == spantree.MAX_DEPTH

    (tree,) = spantree.build(FREEZE)
    at_v1 = "\n".join(spantree.render(tree))
    at_v2 = "\n".join(spantree.render(tree, spantree.max_depth_for("v2")))
    assert "1 deeper span(s) elided" in at_v1
    assert "ProductCatalogService/GetProduct 531800.9ms" not in at_v1
    assert "ProductCatalogService/GetProduct 531800.9ms" in at_v2
    assert "elided" not in at_v2


def test_an_error_spans_status_message_is_printed_and_bounded() -> None:
    """The one thing a span carries that a metric does not (Q94): the service's own reason."""
    failing = span("g", "", "product-catalog", "GetProduct", 0, 2.4, error=True)
    failing = failing.model_copy(
        update={"status_message": "Product Catalog Fail\nFeature Flag Enabled"}
    )
    ok = span("h", "g", "product-catalog", "GetFlag", 1, 1).model_copy(
        update={"status_message": "not an error, not printed"}
    )
    (tree,) = spantree.build([failing, ok])
    text = "\n".join(spantree.render(tree))
    assert "ERROR: Product Catalog Fail Feature Flag Enabled" in text, "one line, whitespace folded"
    assert "not printed" not in text

    long = failing.model_copy(update={"status_message": "x" * 1000})
    (tree,) = spantree.build([long])
    (line,) = [ln for ln in spantree.render(tree) if "ERROR" in ln]
    assert line.endswith("ERROR: " + "x" * spantree.STATUS_MESSAGE_MAX)


def test_a_stored_trace_result_renders_at_the_depth_it_was_read_at() -> None:
    """`max_depth` is stored on the result, so a replay renders what the specialist read. An
    envelope stored before Q94 has no such field and renders at v1's six, as it did."""
    from faultline.tools.results import TraceResult

    stored = TraceResult(service="frontend", spans=FREEZE)
    assert stored.max_depth == spantree.MAX_DEPTH
    assert "1 deeper span(s) elided" in stored.body()

    v2 = TraceResult(service="frontend", spans=FREEZE, max_depth=spantree.max_depth_for("v2"))
    assert "elided" not in v2.body()
    round_tripped = TraceResult.model_validate_json(v2.model_dump_json())
    assert round_tripped.body() == v2.body()
