"""Q94's replay: every rehearsal window still in Tempo, each trace's degrading hop under the rule
as it stood (rules 1-2) and under the rule with the hang rule (0-2), and a healthy control.

    FAULTLINE_TOOLS_WORLD=v2 uv run python hops.py

A fresh `Tools` per query, so one window Tempo no longer holds cannot trip the tool's three-strike
breaker for the windows after it.
"""

from datetime import datetime, timezone

from faultline.tools.settings import ToolSettings
from faultline.tools.spantree import (
    build,
    degrading_hop,
    error_or_self_time_hop,
    max_depth_for,
    render,
)
from faultline.tools.tools import Tools


def at(hhmm):
    h, m = hhmm.split(":")
    return datetime(2026, 9, 24, int(h), int(m), tzinfo=timezone.utc)


now = datetime.now(timezone.utc)
WINDOWS = [
    ("R1 feature_flag", "02:24", "02:46", ("frontend", "product-catalog")),
    ("R2 freeze", "04:03", "04:17", ("frontend", "frontend-proxy", "product-catalog")),
    ("R2b freeze", "06:19", "06:33", ("frontend", "frontend-proxy", "product-catalog")),
    ("R3 partition", "06:50", "07:04", ("frontend", "product-catalog")),
    ("R4 corruption", "07:21", "07:34", ("cart", "checkout")),
    ("R4b corruption", "08:04", "08:19", ("cart", "checkout")),
    ("R5 disk_fill", "08:33", "08:47", ("checkout", "accounting", "kafka")),
    ("freeze bundle", "16:53", "17:04", ("frontend", "frontend-proxy", "product-catalog")),
]
shown_freeze = False
# The control starts at 17:15, well after the freeze's last hung call ended (17:03:14). A "last
# 30 minutes" window reached back into the freeze and replayed its traces as healthy ones.
CONTROL = ("control, healthy", "17:15", None, ("frontend", "checkout", "cart"))
for label, a, b, services in [*WINDOWS, CONTROL]:
    start, end = (at(a), now) if b is None else (at(a), at(b))
    for svc in services:
        for errors in (True,) if b is not None else (True, False):
            result = Tools(ToolSettings()).trace_query(svc, start, end, only_errors=errors)
            tag = f"{label:17} {svc:16} {'errors' if errors else 'all   '}"
            if result.error or not result.spans:
                print(f"{tag} {result.error or 'no traces'}")
                continue
            trees = build(result.spans)
            pairs = [(t, error_or_self_time_hop(t), degrading_hop(t)) for t in trees]
            moved = [(t, o, n) for t, o, n in pairs if (o and o.callee) != (n and n.callee)]
            annotated = [
                (t, o, n)
                for t, o, n in pairs
                if (o and o.callee) == (n and n.callee) and n and n.gave_up
            ]
            print(
                f"{tag} traces={len(trees):3}  callee moved: {len(moved)}  "
                f"same callee, wait added: {len(annotated)}"
            )
            for tree, old, new in moved + annotated:
                started = tree.root.span.started_at.strftime("%H:%M:%S")
                print(
                    f"    {tree.trace_id[:16]} root {started}  was: {old.label() if old else None}"
                )
                print(f"    {' ' * 30}now: {new.label() if new else None}")
            changed = moved
            if label == "freeze bundle" and svc == "frontend" and changed and not shown_freeze:
                shown_freeze = True
                print("    -- first moved trace, rendered at v2's depth --")
                for line in render(changed[0][0], max_depth_for("v2"))[:30]:
                    print("    " + line)
