"""The SREGym adapter (T7.2, ADR-0044), offline.

Registered in `evals/runs/PREREGISTRATION-T7.2-adapter.md` §5: every MCP tool against recorded
replies, the change mapping and its leak guard, the alarm evaluator, the frozen rendering against
a golden text, the tunnel against a local fake proxy, and `McpToolSet` as a `ToolSet`.
"""

from __future__ import annotations

import json
import socket
import threading
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from queue import Queue
from typing import Any, ClassVar

import pytest

from faultline.agents.contracts import Candidate, Verdict
from faultline.agents.evidence import Evidence
from faultline.orchestrator.models import IncidentState, Severity
from faultline.sregym import kube, mcp, opening, profiles, render, toolset, tunnel
from faultline.tools.interface import ToolSet
from faultline.tools.metrics import MetricTemplate
from faultline.tools.results import Trust
from faultline.tools.settings import ToolSettings
from faultline.tools.tools import Tools

T0 = datetime(2026, 10, 3, 12, 0, tzinfo=UTC)
NS = "hotel-reservation"


@pytest.fixture(autouse=True)
def _v2(monkeypatch: pytest.MonkeyPatch) -> None:
    """The driver runs every SREGym application with the identity name map (v2)."""
    monkeypatch.setenv("FAULTLINE_TOOLS_WORLD", "v2")


class FakeClient:
    """`McpClient`'s seam: canned replies per `(server, tool)`, every call recorded."""

    def __init__(self, replies: dict[tuple[str, str], Any]) -> None:
        self.replies = replies
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def call(self, server: str, tool: str, arguments: dict[str, Any]) -> str:
        self.calls.append((server, tool, arguments))
        reply = self.replies[(server, tool)]
        return reply(arguments) if callable(reply) else reply


HOTEL = profiles.profile_by_application("sregym-hotel-reservation")
SOCIAL = profiles.profile_by_application("sregym-social-network")
SHOP = profiles.profile_by_application("sregym-astronomy-shop")


def tools(client: FakeClient, profile: profiles.Profile = HOTEL, **kw: Any) -> toolset.McpToolSet:
    return toolset.McpToolSet(
        client,  # type: ignore[arg-type]
        profile,
        NS,
        ToolSettings(world="v2"),
        now=lambda: T0 + timedelta(minutes=10),
        **kw,
    )


# --- the MCP client, against a local server speaking the HTTP+SSE transport -----------------


class _FakeMcp(BaseHTTPRequestHandler):
    queues: ClassVar[dict[str, Queue[str]]] = {}
    announce = "/prometheus/messages/?session_id=abc"

    def log_message(self, *args: Any) -> None:
        pass

    def do_GET(self) -> None:
        queue: Queue[str] = Queue()
        _FakeMcp.queues["abc"] = queue
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(f"event: endpoint\ndata: {_FakeMcp.announce}\n\n".encode())
        self.wfile.flush()
        while True:
            message = queue.get()
            if message == "":
                return
            self.wfile.write(f"event: message\ndata: {message}\n\n".encode())
            self.wfile.flush()

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.send_response(202)
        self.end_headers()
        queue = _FakeMcp.queues["abc"]
        if body.get("method") == "initialize":
            queue.put(json.dumps({"jsonrpc": "2.0", "id": body["id"], "result": {}}))
        elif body.get("method") == "tools/call":
            name = body["params"]["name"]
            failing = name == "broken"
            text = "boom" if failing else f"called {name} with {body['params']['arguments']}"
            queue.put(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": body["id"],
                        "result": {"content": [{"type": "text", "text": text}], "isError": failing},
                    }
                )
            )
            queue.put("")


@pytest.fixture
def mcp_server() -> Any:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeMcp)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_mcp_client_speaks_the_sse_transport(
    mcp_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    client = mcp.McpClient(mcp_server, timeout=5)
    assert client.call("prometheus", "get_metrics", {"query": "up"}) == (
        "called get_metrics with {'query': 'up'}"
    )


def test_mcp_client_raises_on_a_tool_error(mcp_server: str) -> None:
    with pytest.raises(mcp.McpError, match="reported an error: boom"):
        mcp.McpClient(mcp_server, timeout=5).call("prometheus", "broken", {})


def test_mcp_refuses_an_unknown_server() -> None:
    with pytest.raises(mcp.McpError, match="unknown SREGym MCP server"):
        mcp.McpClient("http://127.0.0.1:1").call("grafana", "x", {})


@pytest.mark.parametrize(
    ("announced", "expected"),
    [
        ("/loki/messages/?session_id=1", "http://h:9954/loki/messages/?session_id=1"),
        ("/messages/?session_id=1", "http://h:9954/loki/messages/?session_id=1"),
        ("http://x/y", "http://x/y"),
    ],
)
def test_endpoint_with_or_without_the_mount(announced: str, expected: str) -> None:
    assert mcp.endpoint_url("http://h:9954", "loki", announced) == expected


def test_replies_are_python_literals_and_errors_are_text() -> None:
    assert mcp.python_literal("{'a': [1, True, None]}") == {"a": [1, True, None]}
    assert mcp.python_literal("None") is None
    with pytest.raises(mcp.McpError):
        mcp.python_literal("__import__('os').system('true')")
    assert mcp.backend_error("[prom_mcp] Error querying get_metrics: x") is not None
    assert mcp.backend_error("{'resultType': 'matrix'}") is None


# --- McpToolSet ---------------------------------------------------------------------------


def test_mcp_tool_set_is_a_tool_set() -> None:
    assert isinstance(tools(FakeClient({})), ToolSet)


def test_a_range_is_one_instant_subquery() -> None:
    seen: list[str] = []

    def metrics(args: dict[str, Any]) -> str:
        seen.append(args["query"])
        return str(
            {
                "resultType": "matrix",
                "result": [{"metric": {"pod": "geo-1"}, "values": [[1.0, "2"], [16.0, "3"]]}],
            }
        )

    result = tools(FakeClient({("prometheus", "get_metrics"): metrics})).promql_query(
        "up", T0, T0 + timedelta(minutes=5), step=15
    )
    assert seen == [f"(up)[300s:15s] @ {(T0 + timedelta(minutes=5)).timestamp():.3f}"]
    assert result.series[0].points == [(1.0, 2.0), (16.0, 3.0)]
    assert result.error is None


def test_a_reported_backend_error_is_an_error_not_data() -> None:
    client = FakeClient({("prometheus", "get_metrics"): "[prom_mcp] Error querying get_metrics: x"})
    result = tools(client).promql_query("up", T0, T0 + timedelta(minutes=5))
    assert result.error is not None and "Error querying" in result.error


def test_metric_baseline_is_tools_own_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """The copied body cannot drift: the same points give the same result as `Tools`."""
    points = [(float(i * 15), 0.01 if i < 30 else 0.4) for i in range(40)]
    monkeypatch.setattr(Tools, "_points", lambda self, *a: list(points))
    ours = tools(FakeClient({}), SHOP)
    monkeypatch.setattr(toolset.McpToolSet, "_points", lambda self, *a: list(points))
    start, end = T0, T0 + timedelta(minutes=10)
    for template in (MetricTemplate.ERROR_RATIO, MetricTemplate.LATENCY_P95):
        theirs = Tools(ToolSettings(world="v2")).metric_baseline("checkout", template, start, end)
        mine = ours.metric_baseline("checkout", template, start, end)
        assert mine.model_dump(exclude={"id"}) == theirs.model_dump(exclude={"id"})


def test_span_templates_are_unavailable_without_span_metrics() -> None:
    result = tools(FakeClient({})).metric_baseline(
        "geo", MetricTemplate.ERROR_RATIO, T0, T0 + timedelta(minutes=5)
    )
    assert result.empty and result.error is not None and "unavailable, not zero" in result.error


def test_runtime_memory_reads_cadvisor_for_the_workload() -> None:
    query = tools(FakeClient({}), SOCIAL).template_query(
        MetricTemplate.RUNTIME_MEMORY, "nginx-web-server"
    )
    assert query is not None
    assert 'pod=~"nginx\\-thrift-([a-z0-9]+-[a-z0-9]+|[0-9]+)"' in query
    assert "container_memory_working_set_bytes" in query and f'namespace="{NS}"' in query


LOKI_TEXT = "\n".join(
    [
        "[2026-10-03 11:59:00] [namespace=hotel-reservation, pod=geo-a-b] before the window",
        "[2026-10-03 12:01:00] [namespace=hotel-reservation, pod=geo-a-b] dial tcp: refused",
        "[2026-10-03 12:02:00] [namespace=hotel-reservation, pod=geo-a-b] retrying",
        "  continued line",
    ]
)


def test_logs_are_filtered_to_the_window_and_selected_by_pod() -> None:
    client = FakeClient({("loki", "get_logs"): LOKI_TEXT})
    result = tools(client).logql_query("geo", T0, T0 + timedelta(minutes=5), contains="dial")
    (_, _, args), *_ = client.calls
    assert args["query"].startswith(f'{{namespace="{NS}",pod=~"geo-')
    assert args["query"].endswith('|= "dial"')
    assert args["last_n_minutes"] == 11
    assert [line.line for line in result.lines] == [
        "dial tcp: refused",
        "retrying\n  continued line",
    ]
    assert not result.truncated


def test_a_full_hundred_lines_is_truncated_even_if_none_fall_in_the_window() -> None:
    lines = [f"[2026-10-03 12:09:{i % 60:02d}] [pod=geo-a-b] line {i}" for i in range(100)]
    client = FakeClient({("loki", "get_logs"): "\n".join(lines)})
    result = tools(client).logql_query("geo", T0, T0 + timedelta(minutes=5))
    assert result.empty and result.truncated


def _jaeger_trace(trace_id: str, started: datetime, error: bool) -> dict[str, Any]:
    us = int(started.timestamp() * 1e6)
    return {
        "traceID": trace_id,
        "processes": {"p1": {"serviceName": "frontend"}, "p2": {"serviceName": "geo"}},
        "spans": [
            {
                "traceID": trace_id,
                "spanID": "a",
                "operationName": "GET /hotels",
                "references": [],
                "startTime": us,
                "duration": 120000,
                "processID": "p1",
                "tags": [],
            },
            {
                "traceID": trace_id,
                "spanID": "b",
                "operationName": "geo.Nearby",
                "references": [{"refType": "CHILD_OF", "spanID": "a"}],
                "startTime": us + 1000,
                "duration": 100000,
                "processID": "p2",
                "tags": [{"key": "error", "type": "bool", "value": error}],
            },
        ],
    }


def test_jaeger_traces_become_span_trees_with_status() -> None:
    reply = str([_jaeger_trace("t1", T0 + timedelta(minutes=1), True)])
    result = tools(FakeClient({("jaeger", "get_traces"): reply})).trace_query(
        "geo", T0, T0 + timedelta(minutes=5)
    )
    child = next(s for s in result.spans if s.span_id == "b")
    assert (child.parent_span_id, child.service, child.error, child.status) == (
        "a",
        "geo",
        True,
        "ERROR",
    )
    assert child.duration_ms == 100.0 and not result.truncated


def test_twenty_traces_is_truncated_and_out_of_window_traces_are_dropped() -> None:
    traces = [_jaeger_trace(f"t{i}", T0 + timedelta(minutes=1), False) for i in range(19)]
    traces.append(_jaeger_trace("old", T0 - timedelta(minutes=30), False))
    result = tools(FakeClient({("jaeger", "get_traces"): str(traces)})).trace_query(
        "geo", T0, T0 + timedelta(minutes=5), only_errors=False
    )
    assert result.truncated and result.traces == 20
    assert "old" not in {s.trace_id for s in result.spans}


def test_an_otel_status_beats_the_error_tag() -> None:
    trace = _jaeger_trace("t1", T0, False)
    trace["spans"][1]["tags"] = [
        {"key": "otel.status_code", "value": "ERROR"},
        {"key": "otel.status_description", "value": "connection refused"},
    ]
    span = toolset.spans_of_jaeger(trace, UTC)[1]
    assert (span.status, span.error, span.status_message) == ("ERROR", True, "connection refused")


# --- the change mapping, and its leak guard ------------------------------------------------


def _rs(revision: int, created: datetime, spec: dict[str, Any], **meta: Any) -> dict[str, Any]:
    return {
        "kind": "ReplicaSet",
        "metadata": {
            "name": f"geo-{revision}",
            "creationTimestamp": created.isoformat().replace("+00:00", "Z"),
            "annotations": {"deployment.kubernetes.io/revision": str(revision), **meta},
            "ownerReferences": [{"kind": "Deployment", "name": "geo"}],
        },
        "spec": {"template": {"metadata": {"annotations": meta}, "spec": spec}},
    }


BEFORE = {
    "dnsPolicy": "ClusterFirst",
    "containers": [
        {
            "name": "hotel-reserv-geo",
            "image": "geo:1",
            "env": [{"name": "DB", "value": "mongodb-geo:27017"}],
            "resources": {"limits": {"memory": "1Gi"}},
        }
    ],
}
AFTER = {
    "dnsPolicy": "None",
    "containers": [
        {
            "name": "hotel-reserv-geo",
            "image": "geo:2",
            "env": [
                {"name": "DB", "value": "mongodb-geo:27018"},
                {"name": "PW", "valueFrom": {"secretKeyRef": {"name": "s", "key": "pw"}}},
            ],
            "resources": {"limits": {"memory": "1Gi"}},
            "readinessProbe": {"tcpSocket": {"port": 9}},
        }
    ],
    "volumes": [{"name": "c", "configMap": {"name": "geo-config"}}],
}


def test_commands_are_fixed_and_read_only() -> None:
    sent = kube.commands(NS)
    assert all(c.startswith("kubectl get ") for c in sent)
    assert not any(" -o json" in c and "secrets" in c for c in sent), "secrets are never JSON"
    with pytest.raises(ValueError):
        kube.commands("x; kubectl delete ns y")


def test_a_revision_diff_names_paths_and_values_by_resource() -> None:
    records = kube.revision_records(
        "geo",
        [_rs(2, T0 + timedelta(minutes=2), AFTER), _rs(1, T0 - timedelta(days=1), BEFORE)],
        T0,
        T0 + timedelta(minutes=5),
    )
    by_summary = {r.summary: r for r in records}
    assert by_summary["containers[hotel-reserv-geo].image changed"].after == "geo:2"
    assert by_summary["containers[hotel-reserv-geo].env[DB] changed"].before == "mongodb-geo:27017"
    secret = by_summary["containers[hotel-reserv-geo].env[PW] changed"]
    assert secret.after is not None and "secretKeyRef" in secret.after, "a reference, never a value"
    assert by_summary["dnsPolicy changed"].resource.value == "container"
    assert by_summary["containers[hotel-reserv-geo].readinessProbe changed"].resource.value == (
        "container"
    )
    assert {r.actor for r in records} == {"platform-automation"}
    assert all(r.at == T0 + timedelta(minutes=2) for r in records)


def test_annotations_and_labels_never_reach_a_record() -> None:
    records = kube.revision_records(
        "geo",
        [
            _rs(1, T0 - timedelta(days=1), BEFORE),
            _rs(2, T0 + timedelta(minutes=1), BEFORE, **{"sregym.io/fault": "wrong_dns_policy"}),
        ],
        T0,
        T0 + timedelta(minutes=5),
    )
    assert records == [], "a metadata-only change is not a pod-spec change"


def test_text_naming_the_benchmark_is_withheld_but_the_record_kept() -> None:
    spec = json.loads(json.dumps(BEFORE))
    spec["containers"][0]["env"][0]["value"] = "chaos-injected"
    (record,) = kube.revision_records(
        "geo",
        [_rs(1, T0 - timedelta(days=1), BEFORE), _rs(2, T0 + timedelta(minutes=1), spec)],
        T0,
        T0 + timedelta(minutes=5),
    )
    assert record.after == "[withheld: names the benchmark]"
    assert record.before == "mongodb-geo:27017"


def test_config_changes_are_names_and_times_only() -> None:
    table = "\n".join(
        [
            "KIND        NAME         CREATED                CHANGED",
            "ConfigMap   geo-config   2026-09-01T00:00:00Z   "
            "2026-09-01T00:00:00Z,2026-10-03T12:03:00Z",
            "ConfigMap   other        2026-09-01T00:00:00Z   2026-10-03T12:03:00Z",
        ]
    )
    records = kube.config_records(
        "geo", table, kube.referenced_config(AFTER), T0, T0 + timedelta(minutes=5)
    )
    assert [(r.summary, r.before, r.after) for r in records] == [
        ("ConfigMap geo-config changed", None, None)
    ]


def test_events_say_only_that_something_happened() -> None:
    events = [
        {
            "involvedObject": {"kind": "Service", "name": "geo"},
            "reason": "InjectedSelectorFault",
            "message": "chaos",
            "lastTimestamp": "2026-10-03T12:01:00Z",
        },
        {"involvedObject": {"kind": "Pod", "name": "geo"}, "lastTimestamp": "2026-10-03T12:01:00Z"},
    ]
    (record,) = kube.event_records("geo", {"geo"}, events, T0, T0 + timedelta(minutes=5))
    assert record.summary == "Service geo: event recorded"


def test_the_change_log_sends_only_its_four_commands() -> None:
    sent: list[str] = []
    outputs = dict(
        zip(
            kube.commands(NS),
            [
                json.dumps(
                    {
                        "items": [
                            _rs(1, T0 - timedelta(days=1), BEFORE),
                            _rs(2, T0 + timedelta(minutes=2), AFTER),
                        ]
                    }
                ),
                json.dumps({"items": []}),
                "KIND NAME CREATED CHANGED",
                json.dumps({"items": []}),
            ],
            strict=True,
        )
    )

    def run(args: dict[str, Any]) -> str:
        sent.append(args["cmd"])
        return outputs[args["cmd"]]

    log = kube.KubernetesChangeLog(
        FakeClient({("kubectl", "exec_kubectl_cmd_safely"): run}),  # type: ignore[arg-type]
        HOTEL,
        NS,
    )
    result = tools(FakeClient({}), changes=log).change_history(
        "geo", T0 - timedelta(hours=1), T0 + timedelta(minutes=5)
    )
    assert set(sent) == set(kube.commands(NS))
    assert result.error is None and len(result.records) >= 4


# --- the opening --------------------------------------------------------------------------


def _vector(*labels: dict[str, str]) -> str:
    return str(
        {"resultType": "vector", "result": [{"metric": m, "value": [1, "1"]} for m in labels]}
    )


def test_alarms_open_one_episode_per_rule_and_service() -> None:
    def metrics(args: dict[str, Any]) -> str:
        q = args["query"]
        if q.startswith("kube_replicaset_owner"):
            return _vector({"replicaset": "geo-7d9", "owner_name": "geo"})
        if q.startswith("kube_pod_owner"):
            return _vector(
                {"pod": "geo-7d9-x", "owner_kind": "ReplicaSet", "owner_name": "geo-7d9"}
            )
        if 'CrashLoopBackOff"}[5m]' in q:
            return _vector({"pod": "geo-7d9-x"})
        if q.startswith("kube_deployment_spec_replicas"):
            return _vector({"deployment": "geo"})
        return _vector()

    opener = opening.Opener(
        FakeClient({("prometheus", "get_metrics"): metrics}),  # type: ignore[arg-type]
        HOTEL,
        NS,
        clock=lambda: T0,
        sleep=lambda _: None,
    )
    incident = opener.open()
    assert incident.state is IncidentState.TRIAGING
    assert sorted((e.alertname, e.service) for e in incident.episodes.values()) == [
        ("KubeDeploymentReplicasMismatch", "geo"),
        ("KubePodCrashLooping", "geo"),
    ]
    assert opener.evaluations == 1 and not opener.fallback


def test_no_alarm_in_five_minutes_falls_back_to_the_front_door() -> None:
    slept: list[float] = []
    opener = opening.Opener(
        FakeClient({("prometheus", "get_metrics"): _vector()}),  # type: ignore[arg-type]
        SOCIAL,
        "social-network",
        clock=lambda: T0,
        sleep=slept.append,
    )
    incident = opener.open()
    (episode,) = incident.episodes.values()
    assert (episode.alertname, episode.service, episode.severity) == (
        "SREGymProblemReported",
        "nginx-web-server",
        Severity.CRITICAL,
    )
    assert opener.evaluations == 6 and slept == [60] * 5 and opener.fallback


def test_faultlines_own_rules_only_where_span_metrics_exist() -> None:
    assert opening.faultline_alarms(HOTEL) == []
    names = [a.name for a in opening.faultline_alarms(SHOP)]
    assert names == ["ServiceHighErrorRate", "ServiceHighLatency", "ServiceNoTraffic"]
    assert all("traces_span_metrics_" in a.expression for a in opening.faultline_alarms(SHOP))


# --- the rendering, frozen ----------------------------------------------------------------


def _evidence(result_id: str, claim: str, **kw: Any) -> Evidence:
    return Evidence(
        kind=kw.pop("kind", "found"),
        claim=claim,
        result_id=result_id,
        specialist="logs",
        service="geo",
        question="why",
        tool="logql_query",
        source="loki",
        trust=Trust.UNTRUSTED,
        raw_sha256="0" * 64,
        **kw,
    )


GOLDEN = """Root cause: geo cannot reach mongodb-geo: its DB address was changed to port 27018
Faulty component: geo
Fault type: bad_config
Confidence: high

Evidence:
- geo dials mongodb-geo:27018, refused (found, from logql_query on geo; query: {pod=~"geo-.*"})
- the old port 27017 still answers (ruled_out, from logql_query on geo; why: not the database)

Reasoning:
The refusals start with the new revision.

Alternatives considered:
1. mongodb-geo: the database is down (dependency_latency). Ranked lower because: it answers on 27017

Open questions:
none"""


def test_the_rendering_matches_its_golden_text() -> None:
    verdict = Verdict(
        root_cause="geo cannot reach mongodb-geo: its DB address was changed to port 27018",
        service="geo",
        fault_class="bad_config",
        remediation_class="config_revert",
        confidence="high",
        evidence=["tr_1", "tr_2", "tr_1"],
        reasoning="The refusals start with the new revision.",
        open_questions=[],
        alternatives=[
            Candidate(
                root_cause="the database is down",
                service="mongodb-geo",
                fault_class="dependency_latency",
                why_not="it answers on 27017",
            )
        ],
    )
    evidence = [
        _evidence("tr_1", "geo dials mongodb-geo:27018, refused", query='{pod=~"geo-.*"}'),
        _evidence(
            "tr_2", "the old port 27017 still answers", kind="ruled_out", note="not the database"
        ),
        _evidence("tr_9", "uncited, so not rendered"),
    ]
    assert render.render(verdict, evidence) == GOLDEN
    assert "config_revert" not in render.render(verdict, evidence), "diagnosis only"


def test_no_verdict_is_a_fixed_sentence() -> None:
    assert render.render(None) == "Faultline reached no verdict."


# --- the tunnel ---------------------------------------------------------------------------


def _serve(handler: Any) -> int:
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen()

    def loop() -> None:
        while True:
            conn, _ = server.accept()
            threading.Thread(target=handler, args=(conn,), daemon=True).start()

    threading.Thread(target=loop, daemon=True).start()
    return int(server.getsockname()[1])


def test_the_tunnel_reaches_its_target_by_connect() -> None:
    def echo(conn: socket.socket) -> None:
        conn.sendall(b"echo:" + conn.recv(100))
        conn.close()

    target = _serve(echo)

    def proxy(conn: socket.socket) -> None:
        request = b""
        while b"\r\n\r\n" not in request:
            request += conn.recv(4096)
        host, port = request.split(b" ")[1].decode().rsplit(":", 1)
        upstream = socket.create_connection((host, int(port)))
        conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        upstream.sendall(conn.recv(100))
        conn.sendall(upstream.recv(100))
        conn.close()

    proxy_port = _serve(proxy)
    t = tunnel.Tunnel("127.0.0.1", target, proxy_url=f"http://127.0.0.1:{proxy_port}").start()
    try:
        with socket.create_connection(("127.0.0.1", t.port), timeout=5) as client:
            client.sendall(b"hello")
            assert client.recv(100) == b"echo:hello"
    finally:
        t.stop()


def test_a_refused_connect_is_an_error() -> None:
    def refuse(conn: socket.socket) -> None:
        conn.recv(4096)
        conn.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
        conn.close()

    port = _serve(refuse)
    with pytest.raises(OSError, match="refused CONNECT"):
        tunnel.connect_via_proxy(f"http://127.0.0.1:{port}", "x", 1)


# --- the CLI's switch ---------------------------------------------------------------------


def test_the_cli_builds_the_sregym_tool_set_only_when_told(monkeypatch: pytest.MonkeyPatch) -> None:
    from faultline.agents import cli

    monkeypatch.setenv("FAULTLINE_TOOLS_BACKEND", "sregym")
    monkeypatch.setenv("MCP_SERVER_URL", "http://host.docker.internal:9954")
    monkeypatch.setenv("FAULTLINE_SREGYM_NAMESPACE", NS)
    monkeypatch.setenv("FAULTLINE_CONTEXT_APPLICATION", "sregym-hotel-reservation")
    built = cli._tool_set("unused")
    assert isinstance(built, toolset.McpToolSet)
    assert isinstance(built._changes, kube.KubernetesChangeLog)

    monkeypatch.delenv("FAULTLINE_TOOLS_BACKEND")
    import psycopg

    monkeypatch.setattr(psycopg, "connect", lambda dsn: object())
    plain = cli._tool_set("dsn")
    assert type(plain) is Tools


def test_every_profile_names_an_application_with_a_snapshot() -> None:
    from faultline.context.graph import APPLICATIONS

    assert {p.application for p in profiles.PROFILES.values()} <= set(APPLICATIONS)
    with pytest.raises(ValueError, match="not in the run"):
        profiles.profile_for("Train Ticket")


def test_the_leak_guard_does_not_withhold_a_default_dns_policy() -> None:
    assert kube._guarded("Default") == "Default"
    assert kube._guarded("chaos-mesh") == "[withheld: names the benchmark]"
    assert kube._guarded("sregym-agent") == "[withheld: names the benchmark]"
