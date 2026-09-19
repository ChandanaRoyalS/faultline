"""`faultline-storm` without a world (T6.7 piece 4): the generator, the refusal, the three passes
against a fake platform, the pre-registration's scoring, and the evidence that refuses rewriting.
The live run is `PREREGISTRATION-T6.7.md`'s business; this file holds the harness to what that
document says it does.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalharness import storm
from faultline.orchestrator.settings import OrchestratorSettings

REPO_ROOT = Path(__file__).resolve().parents[1]
SERVICES = [
    "accountingservice",
    "adservice",
    "cartservice",
    "checkoutservice",
    "currencyservice",
    "emailservice",
    "frontend",
    "paymentservice",
    "productcatalogservice",
    "quoteservice",
    "recommendationservice",
    "shippingservice",
]


# --- the storm itself -----------------------------------------------------------------------------


def test_the_generator_makes_exactly_n_distinct_alerts_over_every_service_and_rule() -> None:
    alerts = storm.generate(200, SERVICES, seed=67)

    assert len(alerts) == 200
    assert len({a.fingerprint for a in alerts}) == 200, "distinct fingerprints"
    pairs = {(a.service, a.alertname) for a in alerts}
    assert pairs == {(s, name) for s in SERVICES for name, _ in storm.ALERT_RULES}
    assert max(a.replica for a in alerts) == 200 // (len(SERVICES) * 3), "one replica per cycle"


def test_the_generator_is_seeded_and_shuffled() -> None:
    a, b, c = (storm.generate(60, SERVICES, seed=s) for s in (1, 1, 2))

    assert a == b
    assert a != c
    assert [x.service for x in a] != sorted(x.service for x in a), "arrival is not catalog order"


def test_the_rules_restated_here_are_the_rules_in_the_locked_file() -> None:
    """`alert-rules.yml` is digest-locked and the harness must not read it; this test does, once,
    so the restatement cannot drift."""
    rules = yaml.safe_load((REPO_ROOT / "compose" / "prometheus" / "alert-rules.yml").read_text())
    declared = {(r["alert"], r["labels"]["severity"]) for g in rules["groups"] for r in g["rules"]}

    assert set(storm.ALERT_RULES) == declared
    assert OrchestratorSettings().max_concurrent == storm.CAP


def test_a_payload_is_an_alertmanager_v4_delivery_the_receiver_accepts() -> None:
    from faultline.ingest.models import WebhookPayload

    alert = storm.generate(1, SERVICES, seed=3)[0]
    onset = datetime(2026, 9, 20, 10, 0, tzinfo=UTC)

    firing = WebhookPayload.model_validate(alert.payload("firing", onset, None))
    resolved = WebhookPayload.model_validate(alert.payload("resolved", onset, onset))

    assert firing.alerts[0].fingerprint == alert.fingerprint
    assert firing.alerts[0].ends_at is None, "Go's zero time reads as still firing"
    assert resolved.alerts[0].episode_key == firing.alerts[0].episode_key, "same episode, resolved"
    assert firing.alerts[0].service_name == alert.service


# --- the refusal ----------------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["http://74.208.194.110:8000", "https://faultline.example.com"])
def test_a_receiver_off_the_loopback_is_refused(url: str) -> None:
    """The deployment's orchestrator investigates every incident it admits; a storm there is a
    bill. The harness cannot be pointed at it."""
    with pytest.raises(storm.NotLoopbackError):
        storm.require_loopback(url)


@pytest.mark.parametrize("url", ["http://localhost:8000", "http://127.0.0.1:8000/"])
def test_the_loopback_is_allowed(url: str) -> None:
    storm.require_loopback(url)


# --- the three passes against a fake platform ---


class FakePlatform:
    """A receiver with dedupe, a stream that drains at once, and an orchestrator that folds every
    alert on the same service into one incident and resolves it on the last resolve."""

    def __init__(self, *, share_an_episode: bool = False) -> None:
        self.seen: set[str] = set()
        self.incidents: dict[str, dict[str, Any]] = {}
        self.posts = 0
        self.share = share_an_episode
        self.queued = 0

    def post(self, payload: dict[str, Any]) -> storm.Posted:
        self.posts += 1
        alert = payload["alerts"][0]
        key = f"{alert['fingerprint']}@{alert['startsAt']}:{alert['status']}"
        if key in self.seen:
            return storm.Posted(200, 0.002, duplicates=1)
        self.seen.add(key)
        service = alert["labels"]["service_name"]
        incident_id = f"inc-{service}"
        row = self.incidents.setdefault(
            incident_id,
            {"state": "triaging", "opened_at": alert["startsAt"], "episodes": set()},
        )
        episode = f"{alert['fingerprint']}@{alert['startsAt']}"
        if alert["status"] == "firing":
            row["episodes"].add(episode)
            if self.share:
                self.incidents.setdefault(
                    "inc-shared",
                    {"state": "triaging", "opened_at": alert["startsAt"], "episodes": set()},
                )["episodes"].add(episode)
        else:
            row["state"] = "resolved"
        open_now = sum(1 for r in self.incidents.values() if r["state"] != "resolved")
        self.queued = max(0, open_now - storm.CAP)
        return storm.Posted(200, 0.004, published=1)

    def sample(self) -> storm.Sample:
        return storm.Sample(0.0, self.queued, 0, self.posts, 0, 0)

    def incidents_since(self, moment: datetime) -> list[storm.IncidentRow]:
        return [
            storm.IncidentRow(
                i, r["state"], r["opened_at"], len(r["episodes"]), sorted(r["episodes"])
            )
            for i, r in self.incidents.items()
        ]

    def container_restarts(self) -> dict[str, int]:
        return {"postgres": 0, "redis": 0}

    def orchestrator_errors(self) -> int:
        return 0


def _run(tmp_path: Path, platform: FakePlatform, n: int = 24) -> storm.StormReport:
    clock = iter(range(0, 100_000))
    return storm.run_storm(
        platform,
        n=n,
        seed=5,
        concurrency=4,
        services=SERVICES[:4],
        evidence_dir=tmp_path / "storm-test",
        clock=lambda: float(next(clock)),
        sleep=lambda _s: None,
    )


def test_three_passes_and_every_prediction_scored(tmp_path: Path) -> None:
    platform = FakePlatform()

    report = _run(tmp_path, platform)

    assert [p.name for p in report.passes] == ["storm", "re-notification", "resolves"]
    assert [p.posts for p in report.passes] == [24, 24, 24]
    assert (report.passes[0].published, report.passes[0].duplicates) == (24, 0)
    assert (report.passes[1].published, report.passes[1].duplicates) == (0, 24)
    assert report.passes[2].published == 24
    assert len(report.incidents) == 4, "one per service in this fake"
    assert {v.prediction.split()[0] for v in report.verdicts} == {f"P{i}" for i in range(1, 11)}
    held = {v.prediction.split()[0]: v.held for v in report.verdicts}
    assert held["P1"] and held["P2"] and held["P3"] and held["P4"] and held["P8"] and held["P10"]
    assert held["P5"] is True, "queue peak 4 - 3 = 1 in this fake, and 0 after the resolves"
    assert held["P6"] and held["P7"] and held["P9"]


def test_a_shared_episode_falsifies_p4_and_the_run_still_records(tmp_path: Path) -> None:
    report = _run(tmp_path, FakePlatform(share_an_episode=True))

    p4 = next(v for v in report.verdicts if v.prediction.startswith("P4"))
    assert p4.held is False
    assert (tmp_path / "storm-test" / "STORM.md").exists()


def test_the_evidence_is_written_and_never_rewritten(tmp_path: Path) -> None:
    _run(tmp_path, FakePlatform())
    evidence = tmp_path / "storm-test"

    assert (evidence / "storm.json").exists() and (evidence / "STORM.md").exists()
    text = (evidence / "STORM.md").read_text()
    assert "PREREGISTRATION-T6.7.md" in text and "| P3 incidents opened in [1, 6] |" in text

    with pytest.raises(SystemExit, match="refusing to rewrite"):
        _run(tmp_path, FakePlatform())


def test_the_pre_registration_exists_and_names_the_ten_predictions() -> None:
    text = (REPO_ROOT / "evals" / "runs" / "PREREGISTRATION-T6.7.md").read_text()
    for i in range(1, 11):
        assert f"| P{i} |" in text, f"P{i}"
    assert "loopback" in text and "$0.00" in text
