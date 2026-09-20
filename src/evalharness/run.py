"""One scored run, as one command (T4.1, ADR-0022 §3).

    uv run python -m evalharness.run cart-dependency-latency

The protocol, in order: **baseline gate**, inject, wait for the orchestrator to correlate,
invoke `faultline-investigate` as the CLI it is, revert, confirm recovery, score. One driver of
the world throughout, enforced by a lock.

**`faultline-investigate` is invoked as a subprocess, not imported.** ADR-0004 keeps benchmark
infrastructure out of the product and ADR-0009 specifies the harness works "through public
interfaces only". Importing the runner would make the harness a second caller of internals that
the CLI's exit codes and stdout already expose - and the exit code is the thing being relied on,
so it has to be the thing being exercised.

**A run that dies is a recorded discard, never a deletion.** ADR-0022 §3.3: if a run is
discarded, the run and the reason are recorded in the results directory. That rule was written
for holdout honesty and it costs nothing to apply everywhere, so it is applied everywhere: the
run directory is created before the gate is read, and whatever happens next is written into it.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from evalharness import freeze, gate, generations, metrics, preflight, prom, variance
from evalharness.prom import PROMETHEUS, QueryError, get_json
from evalharness.provenance import recorder_provenance
from evalharness.scoring import (
    Categories,
    ScoredRun,
    score_label,
    score_ranked,
    score_triage,
)
from evalharness.visibility import target_visibility
from faultline.agents.contracts import SPECIALISTS, unexpected_fields
from injector.worldlock import WorldLock, WorldLockError

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_ROOT = REPO_ROOT / "evals" / "runs"
LOCK_PATH = REPO_ROOT / ".faultline" / "harness.lock"

USD_PER_MTOK_IN = 5.0
USD_PER_MTOK_OUT = 25.0

SCRAPE_INTERVAL_SECONDS = 5
"""Prometheus's scrape interval, from `compose/prometheus/prometheus-config.yaml`.

The unit the correlate wait is denominated in. Not read from that file at runtime because it is
mounted into a container this process does not necessarily have, and a wrong-by-default constant
here would silently shorten every wait - so it is pinned by a test against the config instead."""

CORRELATE_SCRAPES = 180
"""How many scrapes the world gets to produce an alert before "no incident" is honest.

**The wait counts scrapes, not seconds (T7.12).** What it is really asking is whether the world
has had enough chances to alert, and a scrape is that chance. A wall-clock deadline answers a
different question and gets it wrong whenever the two diverge - which they did at T7.11, where a
suspended host let a 900s deadline expire while the world produced sixteen minutes less evidence
than those seconds implied. The scenario was three minutes from paging; the run discarded it.

Derived from what the catalog needs rather than chosen:

* An onset decomposes into the time for the rule's condition to become true plus its `for:`
  clause. T7.11 measured both exactly on `frauddetection-memory-squeeze`: the rate window emptied
  at T+201s, `for: 3m` elapsed, and it fired at T+381s.
* Recorded onsets across all twelve current bundles run **166s to 390s**. Across every recording
  ever archived, **165s to 469s** (n=20).
* The longest `for:` clause in `alert-rules.yml` is **3m**, on `ServiceHighLatency` and
  `ServiceNoTraffic`.

180 scrapes is **900s of world time**: 1.9x the longest onset ever recorded and 2.3x the longest
in the current catalog. That is deliberately the same coverage the old 900s deadline intended -
**the value was never the problem, the unit was** - so this changes when the wait ends without
changing how much evidence it demands.
"""

CORRELATE_CEILING_SECONDS = 1800
"""Wall-clock backstop, so a world that never scrapes again cannot wait forever.

Twice the scrape budget in seconds, which fixes what it can absorb: after T7.11's sixteen-minute
gap, 840s of wall clock remains. That is short of the full 900s allowance but longer than the
longest onset ever recorded (469s), so every scenario in the catalog can still page after an
outage of that size - while a world that has genuinely stopped is bounded at half an hour rather
than forever. A gap longer than about twenty-two minutes exceeds what the ceiling can absorb, and
such a run is discarded as `metrics-gap` - correctly, since it measured nothing either way."""

CORRELATE_GAP_SECONDS = 60
"""No new scrape samples for this long means the world stopped reporting, not that it is quiet.

Twelve scrape intervals. Jitter and a slow scrape lose one or two; losing twelve consecutively is
a different event. T7.11's hole was sixteen minutes across all fifteen services at once."""

CORRELATE_POLL_SECONDS = 20
SETTLE_AFTER_ALERT_SECONDS = 90
"""Once the first episodes land, wait this long before investigating.

Every smoke from T3.4 onward did the same by hand: the first alert opens the incident and the
rest of the blast radius arrives over the following minute or two, so investigating on the first
episode scores triage against an incident that is still filling up."""

RECOVERY_TIMEOUT_SECONDS = 420
RECOVERY_POLL_SECONDS = 30

TRANSIENT_SIGNALS: tuple[str, ...] = (
    "overloaded_error",
    "OverloadedError",
    "rate_limit_error",
    "RateLimitError",
    "Error code: 429",
    "Error code: 500",
    "Error code: 502",
    "Error code: 503",
    "Error code: 504",
    "Error code: 529",
    "APIConnectionError",
    "APITimeoutError",
)
"""Failures worth trying again: the provider was busy, not the request was wrong.

**A 400 is deliberately absent.** `invalid_request_error` covers a malformed request and an
exhausted credit balance, and both are terminal - T4.1's second run died on the latter and
retrying it would have burned three more world injections to learn the same thing.
"""

RETRY_DELAYS_SECONDS: tuple[int, ...] = (20, 60, 120)
"""Three attempts after the first, at widening delays. **Small and fixed, not adaptive.**

Sized against what a retry costs *here* rather than against a service-level objective. A retry is
cheap - the fault is still injected and the incident still exists, so only the investigation
repeats - while the alternative is what the first sweep paid: a 529 on the first model call cost
an injection, a correlation wait, a revert and ten minutes, for one scenario slot.

Widening because a provider that is busy now is often busy in twenty seconds; three because a
provider still refusing after three and a half minutes is having an outage, and a sweep should
report that rather than sit in it.
"""


def counts_toward_aggregates(manifest: dict[str, Any]) -> bool:
    """Whether a run may be counted in any figure that leaves this repository.

    **A demo run is a normal run that no aggregate may count.** It passes the same gate,
    reverts the same way and is recorded the same way - the only thing it is not is a sample.
    Demos get re-run to be watched, on whichever scenario tells the best story, so counting
    them would quietly weight the numbers toward the scenario chosen for being watchable.

    One predicate rather than a convention, because "remember to exclude the demo" is the kind
    of rule that holds until the first person who did not know it writes the next aggregate.

    **An adversarial run is the second thing no aggregate may count** (T6.8). It is a dev scenario
    with a second attacker planted in the world, and its diagnosis score is reported beside its
    injection score in the evidence directory - never in a table that a run without the attacker
    also appears in. The key is the manifest's `adversarial` block, written by `main` when
    `--adversarial` was passed.
    """
    return not manifest.get("demo", False) and "adversarial" not in manifest


STANDING_PIPELINE_KEYS = ("baseline", "ablation", "exclusion_policy")
"""What makes a run something other than the standing pipeline. **Named, so the next one is.**"""


def is_standing_pipeline(manifest: dict[str, Any]) -> tuple[bool, str]:
    """Whether this run is the full pipeline in its standing configuration, and why not.

    **Q66's shared predicate, built after the fifth copy learned it the same way as the first
    four.** `scenario_table._qualifies` carries a comment counting three occasions when a key
    joined `evaldb.FINGERPRINT_INPUTS` and this repository's *other* run filters did not learn
    about it: arm B's first six runs landing in arm A's column, `observability_digest` two days
    earlier, the B0 arm before that. T6.5's donor selection was the fourth. Its own row ended
    *"what is not acceptable is a fifth copy learning it the same way"* - and `exclusion_policy`
    joined the fingerprint on 2026-09-17 and reached this filter on 2026-09-18, after sixty runs
    of two arms pooled into one README row.

    `counts_toward_aggregates` made this argument one function above, for demo runs: *"one
    predicate rather than a convention, because 'remember to exclude the demo' is the kind of rule
    that holds until the first person who did not know it writes the next aggregate."* It was
    right, and it was never extended past the axis it was written for.

    **Returns why, not just whether**, because the three callers each want to say something
    different to a different reader: a table drops the run silently, a drafter refuses with a
    message, and a report names what it excluded.

    **An absent key reads as standing**, which is every run made before that key existed. That is
    deliberate and it is the weak spot: a run predating an axis is indistinguishable from one that
    declared the standing value, and `evaldb`'s `missing` column is the only place the difference
    is visible.
    """
    baseline = manifest.get("baseline")
    if baseline:
        # `str()` because it is a label on the manifest and a block on some verdict artifacts.
        # A predicate that crashed on the shape would be a filter that does not filter.
        return False, f"a {str(baseline).upper()} baseline, which is a control"
    ablation = manifest.get("ablation") or []
    if ablation:
        return False, f"an ablation run ({', '.join(sorted(ablation))} withheld)"
    policy = manifest.get("exclusion_policy") or "own"
    if policy != "own":
        return False, f"a {policy!r} retrieval arm, which reads a narrower corpus (T6.5 §4)"
    return True, ""


EVENT_PREFIX = "@@EVENT "
"""Marks a machine-readable progress line on stdout.

The demo narrates a live run, and the alternative was scraping this module's prose - which
would make every print statement here a compatibility surface, silently broken by rewording.
An explicit event line is a contract that can be pinned by a test instead.
"""


def emit(enabled: bool, event: str, **fields: Any) -> None:
    """One progress event, when a narrator asked for them. A no-op for every ordinary run."""
    if enabled:
        print(EVENT_PREFIX + json.dumps({"event": event, **fields}), flush=True)


class RunError(RuntimeError):
    """The run cannot continue. The reason is recorded as a discard before this escapes.

    `discard_reason` is what the manifest records. Subclasses narrow it so that outcomes which
    mean different things are distinguishable after the fact rather than sharing one label -
    see `WorldStoppedReportingError` and `NoAlertError` (T7.12).
    """

    discard_reason = "run failed"


class RunDir:
    """Where a run's artifacts land, and where its discard is recorded if it has one."""

    def __init__(self, run_id: str, root: Path = RUN_ROOT) -> None:
        self.run_id = run_id
        self.path = root / run_id
        self.path.mkdir(parents=True, exist_ok=True)
        self.manifest: dict[str, Any] = {"run_id": run_id}

    def write(self, name: str, content: str) -> Path:
        target = self.path / name
        target.write_text(content)
        return target

    def save_manifest(self) -> Path:
        return self.write("manifest.json", json.dumps(self.manifest, indent=2, default=str) + "\n")

    def invalidate(self, reason: str, detail: str = "") -> Path:
        """**Marked invalid, not merely annotated** (T4.1b).

        Distinct from `discard`. A discarded run produced no result; an invalid run produced one
        that must not be counted, and the difference is worth keeping in the file name because
        the two answer different questions about a catalog: how often the harness fails, and how
        often it produced a number nobody may use. The artifacts stay in both cases.
        """
        self.manifest["invalid"] = {"reason": reason, "at": datetime.now(UTC).isoformat()}
        self.save_manifest()
        return self.write(
            "INVALID.md",
            f"# Invalid run\n\n**Reason:** {reason}\n\n"
            f"The run completed and was scored. **Its numbers must not be used**, and it is "
            f"kept rather than deleted so that the count of invalid runs is itself a fact "
            f"(T4.1b, ADR-0008 axis 2).\n\n{detail}\n",
        )

    def refuse(self, reason: str, detail: str = "") -> Path:
        """A run the gate would not let start. **Recorded, and not a discard.**

        `GateRefusedError`'s own docstring says it: *"The world is not fit to inject into. Nothing
        was injected."* A discard is a run that **happened** and produced no result; this is a run
        that never started, and conflating them inflates the one number ADR-0022 §3.3 keeps
        visible so that it means something.

        **Measured, and it was exactly half.** Of 44 discards on disk, 22 carried no `injected_at`
        - 10 `baseline gate refused`, 10 `pipeline-down`, 2 others. So the headline discard rate
        this repository has been quoting and budgeting against, **33%, was double the truth of
        16.7%.** `HeadroomExhaustedError` had already made this argument for itself and carried
        `is_pause` to act on it; nothing carried it for the other refusals.

        **Nothing on disk is rewritten.** Those 22 manifests keep the label they were written
        with; the distinction is recoverable from `injected_at`, which every manifest already has,
        so the correct figure is a *reading* of the record rather than an edit to it.
        """
        self.manifest["refused"] = {"reason": reason, "at": datetime.now(UTC).isoformat()}
        self.save_manifest()
        return self.write(
            "REFUSED.md",
            f"# Refused run\n\n**Reason:** {reason}\n\n"
            f"**Nothing was injected and this scenario was not attempted.** This is not a "
            f"discard: a discard is a run that happened and produced no result. Recorded rather "
            f"than deleted, so a refusal that recurs is visible as a pattern.\n\n{detail}\n",
        )

    def discard(self, reason: str, detail: str = "") -> Path:
        """**Recorded, not deleted.** The directory stays and says why it is not a result.

        For a run that **started**. A gate refusal uses `refuse` - see its docstring for the
        measurement that separated them.
        """
        self.manifest["discarded"] = {"reason": reason, "at": datetime.now(UTC).isoformat()}
        self.save_manifest()
        return self.write(
            "DISCARDED.md",
            f"# Discarded run\n\n**Reason:** {reason}\n\n"
            f"Recorded rather than deleted, per ADR-0022 §3.3: a discarded run and its reason "
            f"stay in the results directory, so the number of runs is a fact nobody can hide "
            f"by tidying.\n\n{detail}\n",
        )


def previous_run_manifest(before: str, root: Path = RUN_ROOT) -> dict[str, Any] | None:
    """The manifest of the most recent run started before `before`. None if there is not one.

    Run directories are `<UTC timestamp>-<scenario>`, so lexical order is chronological.
    """
    if not root.is_dir():
        return None
    for path in sorted((d for d in root.iterdir() if d.is_dir() and d.name < before), reverse=True):
        manifest = path / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            loaded: dict[str, Any] = json.loads(manifest.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        return loaded
    return None


def _kafka_uptime(manifest: dict[str, Any] | None) -> int | None:
    if not manifest:
        return None
    headroom = (manifest.get("baseline_gate") or {}).get("headroom") or {}
    seconds = headroom.get("uptime_seconds")
    return int(seconds) if isinstance(seconds, int) else None


def sweep_block(
    sweep: str | None, slot: int | None, of: int | None, pass_number: int | None
) -> dict[str, Any] | None:
    """Where this run sat in the sweep that launched it, or `None` when nothing launched it.

    **548 manifests and not one of them says which sweep it belongs to** (Q60). `RESULTS.md`
    groups its headline figures under *"dev sweep 12"*, a name that exists in prose and nowhere in
    the record; the only way to recover a sweep's membership today is timestamp arithmetic across
    manifests, which a resumed or interleaved sweep breaks.

    **`id` is the sweep's, not the run's.** A resume passes the original id back with `--label`, so
    the record it joins is the one it is continuing rather than a second sweep that looks like it.

    **`slot` is the whole sweep's numbering, not the resumed remainder's** - a resumed pass 2 of 3
    is slot 11 of 30 - because `sweep()` already prints it that way and two numberings for one run
    is how a reader ends up with two answers.

    `pass_number` is recorded rather than derived. `slot // len(catalog)` is right only when no
    scenario was added or removed between passes, and the catalog is not frozen.
    """
    if not sweep:
        return None
    return {"id": sweep, "slot": slot, "of": of, "pass": pass_number}


def world_continuity(run_id: str, uptime_now: int | None, root: Path = RUN_ROOT) -> dict[str, Any]:
    """Whether the world this run measures is the same instance the previous run measured.

    **A recorded event with a cause, not a discontinuity to be inferred from (T7.33).** T7.32 left
    a recycle visible only as a `percent_now` that fell rather than rose, which cannot be told
    apart from a missing sample, a reordered manifest, or a restart nobody chose. An uptime that
    resets is unambiguous, and pairing it with the previous run's outcome names *why*:

    - the previous run **paused** on the headroom gate, and kafka is younger -> a deliberate
      recycle, the operator clearing a refusal the gate asked them to clear;
    - kafka is younger and nothing paused -> **a restart nobody recorded**, which is worth
      surfacing rather than smoothing over;
    - no previous run, or no reading in it -> `unknown`, said plainly instead of assumed continuous.
    """
    previous = previous_run_manifest(run_id, root)
    before = _kafka_uptime(previous)
    restarted = None if (before is None or uptime_now is None) else uptime_now < before
    if restarted is None:
        cause = "unknown - no comparable reading in the previous run"
    elif not restarted:
        cause = "continuous - same kafka instance as the previous run"
    elif previous is not None and previous.get("paused"):
        cause = "deliberate recycle - the previous run paused on the headroom gate and was cleared"
    else:
        cause = "restarted, and no run recorded a pause before it - cause not established here"
    return {
        "kafka_uptime_seconds": uptime_now,
        "kafka_uptime_seconds_previous_run": before,
        "previous_run_id": None if previous is None else previous.get("run_id"),
        "kafka_restarted_since_previous_run": restarted,
        "cause": cause,
        "note": (
            "A sweep spanning a restart did not run every scenario against the same kafka "
            "instance. That is a resource level, not a code or config change - no digest moves "
            "and the runs describe the same world (T7.33)."
        ),
    }


def _sh(args: list[str], env: dict[str, str] | None = None, timeout: int = 1800) -> tuple[int, str]:
    merged = {**os.environ, **(env or {})}
    result = subprocess.run(
        args, capture_output=True, text=True, check=False, env=merged, timeout=timeout
    )
    return result.returncode, result.stdout + result.stderr


def open_incidents(dsn: str) -> list[str]:
    import psycopg

    from faultline.orchestrator.models import TERMINAL

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        # Derived from `TERMINAL`: `DUPLICATE_MERGED` is an end state too, and the literal
        # pair this replaced would have read a merged incident as open forever.
        cur.execute(
            "SELECT id FROM incidents WHERE NOT (state = ANY(%s))",
            ([st.value for st in TERMINAL],),
        )
        return [row[0] for row in cur.fetchall()]


def settling_incidents(dsn: str) -> list[tuple[str, datetime]]:
    """Incidents that have resolved but whose settle window may not have elapsed (T4.13).

    The window itself is the gate's to apply - this asks for a generous superset and lets one
    place decide what "still settling" means. `resolved_at` is stored as the observable moment
    the last episode cleared, which is the same clock the orchestrator reopens against.
    """
    import psycopg

    horizon = now_utc() - gate.settle_window() * 2
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, resolved_at FROM incidents "
            "WHERE resolved_at IS NOT NULL AND resolved_at >= %s",
            (horizon,),
        )
        return [(row[0], row[1]) for row in cur.fetchall()]


def now_utc() -> datetime:
    return datetime.now(UTC)


def expected_episodes(bundle: dict[str, Any]) -> int:
    """How many episodes to wait for, read from the bundle rather than assumed.

    **The first sweep discarded a scenario over this.** `min_episodes` was hard-coded to 2, and
    `frauddetection-memory-squeeze` alerts on exactly one service - `frauddetectionservice`, and
    nothing downstream, because a sparse service failing quietly pages nobody else. It could
    never have satisfied the wait, so it timed out at 900s and was recorded as though the world
    had not reacted. The world reacted exactly as its bundle says it does.

    Two is still right where the blast radius is wider: it is the cheapest signal that the radius
    is filling rather than that one alert arrived early. So: two, or the whole radius if the
    radius is smaller than two.
    """
    services = {
        entry.get("service")
        for entry in bundle.get("alerts_over_window") or ()
        if entry.get("service")
    }
    return min(2, max(1, len(services)))


class WorldStoppedReportingError(RunError):
    """The world stopped producing telemetry for long enough that the wait proved nothing.

    **A different finding from "the fault did not fire", and until T7.12 they shared a message.**
    A run that ends this way measured nothing about its scenario: the fault may have been about
    to page, as T7.11 established it was. Recorded with its own discard reason so the two are
    distinguishable in the manifest afterwards.
    """

    discard_reason = "metrics-gap"


class NoAlertError(RunError):
    """The world reported throughout its scrape budget and the fault still did not page.

    The genuine negative result, and the only one of the two that says anything about the
    scenario. T7.11's discard was recorded under this meaning while actually being the other one.
    """

    discard_reason = "no-alert"


def scrapes_over(window_seconds: int) -> int | None:
    """How many scrape samples any target produced over the trailing window.

    `up` is synthetic, present for every target, and appended once per scrape - so counting its
    samples counts scrapes directly, which is the quantity the wait actually cares about. `max`
    across targets rather than `sum`, so the number stays in units of scrapes as targets come and
    go. Measured at 12 per minute against the 5s interval (T7.12).

    Deliberately not `prometheus_tsdb_head_samples_appended_total`: this deployment does not
    scrape Prometheus itself, so that counter is absent here. `None` means the question could not
    be asked at all, which is not the same as zero and the caller treats it differently.
    """
    try:
        payload = get_json(
            PROMETHEUS,
            "/api/v1/query",
            {"query": f"max(count_over_time(up[{window_seconds}s]))"},
        )
        result = payload.get("data", {}).get("result", [])
        return int(float(result[0]["value"][1])) if result else 0
    except (QueryError, OSError, KeyError, IndexError, ValueError):
        return None


def wait_for_incident(dsn: str, after: datetime, min_episodes: int = 2) -> str:
    """Poll for an incident the orchestrator opened after the injection.

    **The budget is scrapes, not seconds (T7.12).** What the wait is really asking is whether the
    world has had enough chances to alert, and a chance is a scrape. Denominated in wall clock,
    the wait spends its budget while a suspended host produces nothing - which is precisely how
    T7.11 lost `frauddetection-memory-squeeze`, a scenario that pages reliably at T+390s, to a
    sixteen-minute telemetry gap inside a 900s deadline. A clock cannot notice that; a scrape
    count cannot miss it.

    So a gap does not end the wait - it fails to advance it. The same sixteen minutes now costs
    zero of the 180 scrapes, the world resumes, and the alert arrives inside the budget. Two
    things bound the wait besides: `CORRELATE_CEILING_SECONDS` so a dead world cannot hold the
    harness forever, and the gap accounting below so that when the ceiling *is* what stopped us,
    the run is discarded as `metrics-gap` rather than as evidence about the fault.

    Harness-side only: this function reads no prompt and no contract, so `runtime_version` does
    not move. See `faultline.agents.stamp`.
    """
    import psycopg

    started = time.monotonic()
    ceiling = started + CORRELATE_CEILING_SECONDS
    last_advance_at = started
    scrapes = 0
    longest_gap = 0.0

    while True:
        with psycopg.connect(dsn) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT i.id, count(e.*) FROM incidents i "
                "LEFT JOIN incident_episodes e ON e.incident_id = i.id "
                "WHERE i.state = 'triaging' AND i.opened_at >= %s GROUP BY i.id",
                (after,),
            )
            for incident_id, episodes in cur.fetchall():
                if episodes >= min_episodes:
                    print(f"  incident {incident_id} with {episodes} episode(s)")
                    return str(incident_id)

        now_mono = time.monotonic()
        elapsed = now_mono - started
        # Ask over the whole elapsed wait rather than per-poll, so nothing is double-counted or
        # dropped at a window boundary. Range windows this size are cheap and the number is
        # monotonic by construction.
        seen = scrapes_over(max(SCRAPE_INTERVAL_SECONDS, int(elapsed) + 1))
        if seen is not None and seen > scrapes:
            scrapes = seen
            last_advance_at = now_mono
        longest_gap = max(longest_gap, now_mono - last_advance_at)

        if scrapes >= CORRELATE_SCRAPES:
            break  # the world had its chances and did not take them
        if now_mono >= ceiling:
            break  # backstop: the world is not coming back

        time.sleep(CORRELATE_POLL_SECONDS)

    waited = time.monotonic() - started
    if scrapes < CORRELATE_SCRAPES or longest_gap >= CORRELATE_GAP_SECONDS:
        raise WorldStoppedReportingError(
            f"the world stopped reporting: {scrapes} of {CORRELATE_SCRAPES} scrapes in "
            f"{waited:.0f}s wall clock, longest gap {longest_gap:.0f}s. This run measured nothing "
            "about its scenario and is NOT evidence that the fault does not alert - T7.11 found a "
            "sixteen-minute telemetry gap behind exactly this shape, on a scenario that pages "
            "reliably at T+390s. Check whether the host suspended."
        )
    raise NoAlertError(
        f"no incident reached {min_episodes} episode(s) within {CORRELATE_SCRAPES} scrapes "
        f"({waited:.0f}s wall clock, no telemetry gap seen - the world was reporting throughout). "
        "The fault may not alert on this world - check the bundle's alerts_over_window, and note "
        "that a sparse service can take far longer than a busy one to trip a rule "
        "(evals/scenarios/CATALOG.md)."
    )


CALLER_PROBE_WINDOW_SECONDS = 120
"""How far back the caller probe looks. Two minutes: long enough for a scrape or two after the
revert, short enough that it is reading the world *after* recovery rather than during the fault."""


def caller_reachability(service: str, *, now: datetime | None = None) -> dict[str, Any]:
    """**Observational only. Refuses nothing, gates nothing** (Q32).

    `confirm_recovery` asks whether alerts stopped and services report. It does not ask whether a
    container the revert *recreated* is being **reached**. After `shipping-wrong-image`'s revert,
    frontend's gRPC client kept dialling the old container's address (`172.18.0.7:50050`), and the
    next scenario - `ad-memory-squeeze`, first in the catalog where shipping is last - opened with
    frontend's shipping-quote calls refused. Two of its four misses across dev sweep 12's arms cite
    that address and the previous scenario's image change.

    **This does not fix that, and is not built to.** There is no caller-to-callee metric in this
    world: `ERROR_RATIO` and `CALL_RATE` are per service, so "frontend cannot reach shipping" has
    to be inferred from frontend's own error ratio. Whether that inference actually shows the
    condition **has never been measured** - the race has been observed once, on a live sweep.

    A recovery gate built on an unmeasured signal is a check that may never fire, reads as
    protection, and gets trusted. This repository has shipped that three times in a fortnight: a
    retrieval gate that could not run, a probe still measuring an arm that had been replaced, and a
    falsification bound to one strength of an effect. So this records and does not decide.

    The trigger in Q32's row - a sweep running `shipping-wrong-image` and `ad-memory-squeeze` back
    to back - then produces evidence about whether the signal exists. **Gate on it after that, not
    before.**
    """
    from faultline.context.graph import ServiceGraph
    from faultline.telemetry import PROMETHEUS, query_range
    from faultline.tools.metrics import MetricTemplate, render_query

    end = now or datetime.now(UTC)
    start = end - timedelta(seconds=CALLER_PROBE_WINDOW_SECONDS)
    try:
        graph = ServiceGraph.from_snapshot()
        callers = sorted(graph.neighbours(service)) if graph.has(service) else []
    except Exception as exc:  # pragma: no cover - a missing snapshot must not fail a run
        return {"service": service, "error": f"{type(exc).__name__}: {exc}", "callers": {}}

    readings: dict[str, Any] = {}
    for caller in callers:
        try:
            payload = query_range(
                render_query(MetricTemplate.ERROR_RATIO, caller),
                start,
                end,
                step=15,
                base=PROMETHEUS,
            )
            points = prom.series_points(payload)
            values = [v for series in points.values() for _, v in series]
            readings[caller] = max(values) if values else None
        except Exception as exc:  # pragma: no cover - observational; never fails a run
            readings[caller] = f"{type(exc).__name__}"

    return {
        "service": service,
        "window_seconds": CALLER_PROBE_WINDOW_SECONDS,
        "callers": readings,
        "note": "observational (Q32); nothing refuses on this",
    }


def confirm_recovery() -> gate.GateReading:
    """The gate, run again after the revert. Same checks, so recovery means the same thing
    quiet meant.

    **Deliberately without the incident arguments.** Recovery asks whether the world came back,
    not whether the store is ready to receive a new injection. This run's own incident has just
    resolved, so it is inside the settle window by construction (T4.13) and passing it here
    would make every run fail its own recovery check. The settle-window refusal belongs to the
    baseline gate, which is the one deciding whether it is safe to inject.
    """
    deadline = time.monotonic() + RECOVERY_TIMEOUT_SECONDS
    reading = gate.read()
    while time.monotonic() < deadline and not reading.passed:
        time.sleep(RECOVERY_POLL_SECONDS)
        reading = gate.read()
    return reading


def bundle_for(scenario_id: str) -> dict[str, Any]:
    for split in ("dev", "holdout"):
        path = REPO_ROOT / "evals/scenarios/artifacts" / split / scenario_id / "manifest.json"
        if path.exists():
            return dict(json.loads(path.read_text()))
    raise RunError(f"no recorded bundle for {scenario_id}")


def also_correct_fixes(scenario_id: str) -> frozenset[str]:
    """Remediations besides the labelled one that were **measured** to fix this fault (T7.17).

    Read from the scenario file at scoring time rather than from the bundle, because it is a
    scoring policy and not a property of the recording: no bundle carries it, and none is
    re-recorded to gain it. Deliberately outside `scenario_fingerprint` for the same reason - the
    labelled `expected_remediation_class` is unchanged, so no bundle is invalidated by this.

    The applied set is written into the scored output, so a report says which one it used rather
    than leaving a reader to infer it from the catalog as it stands today.
    """
    path = REPO_ROOT / "evals/scenarios" / f"{scenario_id}.yaml"
    if not path.exists():
        return frozenset()
    from evalharness.scenario import Scenario

    return frozenset(r.value for r in Scenario.from_yaml(path).also_correct_remediation)


def culprit_service(scenario_id: str) -> str:
    """The service the injector actually broke, canonicalised (T4.2).

    Read from the scenario file at scoring time, exactly as `also_correct_fixes` is and for the
    same reason: this is a **scoring policy**, not a property of the recording. No bundle carries
    it, none is re-recorded to gain it, and it stays outside `scenario_fingerprint` so no
    previously recorded bundle is invalidated by scoring a new axis over it.

    `canonical_service` because the scenario names a compose service (`ad-service`) and the agent
    names an OTel `service.name` (`adservice`). ADR-0017 makes that one identity; comparing the
    two raw strings would score every correct answer wrong.
    """
    path = REPO_ROOT / "evals/scenarios" / f"{scenario_id}.yaml"
    if not path.exists():
        return ""
    from evalharness.scenario import Scenario
    from injector.world import canonical_service

    return str(canonical_service(Scenario.from_yaml(path).injection.target))


def read_trajectory_facts(dsn: str, trajectory_id: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*), coalesce(sum(tokens_in),0), coalesce(sum(tokens_out),0) "
            "FROM trajectory_steps WHERE trajectory_id = %s",
            (trajectory_id,),
        )
        steps, tin, tout = cur.fetchone() or (0, 0, 0)
        cur.execute(
            "SELECT model, runtime_version, budget_exhausted FROM trajectories WHERE id = %s",
            (trajectory_id,),
        )
        row = cur.fetchone() or ("", "", False)
    return {
        "steps": int(steps),
        "tokens_in": int(tin),
        "tokens_out": int(tout),
        "model": row[0],
        "runtime_version": row[1],
        "budget_exhausted": bool(row[2]),
    }


def metric_panel(dsn: str, trajectory_id: str) -> metrics.MetricPanel:
    """T4.3's panel, read from what the run already stored.

    One connection, four reads, no writes and no new columns. The plan's method column claimed
    *"no new instrumentation needed because P2 recorded everything"* and this function is where
    that claim is either true or not: it is true, and the one place it was nearly not is tool-call
    validity, which lives in the envelope's opening tag rather than in a column of its own.
    """
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT extract(epoch FROM (ended_at - started_at)) FROM trajectories WHERE id = %s",
            (trajectory_id,),
        )
        row = cur.fetchone()
        # `ended_at` is NULL for a trajectory that never finished - a crashed run, which is
        # discarded rather than scored. Zero rather than a guess; the panel says steps too.
        wall_ms = int(float(row[0]) * 1000) if row and row[0] is not None else 0

        cur.execute(
            "SELECT kind, coalesce(sum(latency_ms),0), count(*) FROM trajectory_steps "
            "WHERE trajectory_id = %s GROUP BY kind",
            (trajectory_id,),
        )
        by_kind = {str(kind): (int(total), int(n)) for kind, total, n in cur.fetchall()}

        cur.execute(
            "SELECT c.tool, c.request, c.envelope FROM trajectory_tool_calls c "
            "JOIN trajectory_steps s ON s.trajectory_id = c.trajectory_id AND s.seq = c.seq "
            "WHERE c.trajectory_id = %s ORDER BY c.seq",
            (trajectory_id,),
        )
        calls = [(str(tool), request or {}, str(envelope)) for tool, request, envelope in cur]

        cur.execute(
            "SELECT payload FROM trajectory_steps WHERE trajectory_id = %s "
            "AND payload ? 'disclosure' ORDER BY seq DESC LIMIT 1",
            (trajectory_id,),
        )
        found = cur.fetchone()
        disclosure = (found[0] or {}).get("disclosure") if found else None

        cur.execute(
            "SELECT payload FROM trajectory_steps WHERE trajectory_id = %s "
            "AND payload ? 'violations' ORDER BY seq DESC LIMIT 1",
            (trajectory_id,),
        )
        found = cur.fetchone()
        narrative = (found[0] or {}) if found else {}

    tool_ms, _ = by_kind.get("tool_call", (0, 0))
    completion_ms, _ = by_kind.get("completion", (0, 0))
    return metrics.MetricPanel(
        latency=metrics.Latency(
            investigation_ms=wall_ms,
            tool_ms=tool_ms,
            model_ms=completion_ms,
            steps=sum(n for _, n in by_kind.values()),
        ),
        tools=metrics.tool_calls(calls),
        context=metrics.briefings(disclosure),
        citation_violations=len(narrative.get("violations", []) or []),
        narrative_regenerated=bool(narrative.get("regenerated", False)),
        narrative_escalated=bool(narrative.get("escalated", False)),
    )


def retrieval_enforcement(
    dsn: str, trajectory_id: str, own_origin: str | None = None
) -> dict[str, Any]:
    """Did the leave-one-out filter actually remove anything? (T4.1b)

    T4.1b's second half: *"the count of filtered artifacts is logged per run, and a scored run
    where the filter did not fire is marked invalid, not merely annotated - silent
    non-enforcement is how this defect returns."*

    Three outcomes, and the third is the one that matters:

    - **no benchmark retrieval** - every row has an empty `exclude_origins`. This is the product
      case and it is legal; a live incident has no origin to exclude.
    - **fired** - every excluding row removed at least one chunk.
    - **did not fire** - a row asked for an exclusion and it matched **nothing**. On a scored dev
      run the scenario's own narrative is in the corpus by construction, so a zero says either
      the corpus does not hold it or the exclusion did not apply to it. Either way the run's
      leave-one-out claim is unsupported and the run is not a result.

    **A fourth since T6.5, and it is the reason this function now takes `own_origin`.** The
    exclusion is a set, so a positive `excluded_count` no longer means *S's own artifacts were
    unreachable* - a WITHOUT-arm run excluding three same-class scenarios reports a healthy count
    whether or not S is among them. `own_origin` is checked against the recorded set directly,
    which is the assertion ADR-0008 axis 2 actually makes; the count says only that the exclusion
    had something to bite on. Passing `None` skips that check and is for callers that do not know
    which scenario was under test.

    `NULL` counts are *not computed*, not zero: rows written before this task, and any store
    that cannot count. They are reported as `unassessable` and never invalidate a run, because
    refusing a run on a number nobody recorded would be inventing enforcement rather than
    performing it.
    """
    import psycopg

    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT seq, exclude_origins, excluded_count FROM trajectory_retrievals "
            "WHERE trajectory_id = %s ORDER BY seq",
            (trajectory_id,),
        )
        rows = cur.fetchall()
    return classify_retrievals(
        [(int(seq), list(origins or []), count) for seq, origins, count in rows],
        own_origin=own_origin,
    )


def classify_retrievals(
    rows: list[tuple[int, list[str], int | None]], own_origin: str | None = None
) -> dict[str, Any]:
    """The judgement, separated from the query so it can be tested without a database.

    `rows` is `(seq, exclude_origins, excluded_count)` as stored. Kept pure deliberately: the
    decision to refuse a run is the part that has to be right, and a rule reachable only through
    Postgres is a rule exercised only by the integration suite.

    **`missing_own` is T6.5's addition and it is the strict one.** A row that excluded something
    but not the scenario under test has not made ADR-0008 axis 2's assertion, however healthy
    its count looks. It invalidates the run for the same reason `silent` does, and it is reported
    separately so a reader can tell *the corpus was empty* from *we excluded the wrong things*.
    """
    excluding = [(seq, origins, count) for seq, origins, count in rows if origins]
    silent = [(seq, origins) for seq, origins, count in excluding if count == 0]
    unassessable = [(seq, origins) for seq, origins, count in excluding if count is None]
    missing_own = (
        [(seq, origins) for seq, origins, _ in excluding if own_origin not in origins]
        if own_origin is not None
        else []
    )
    return {
        "retrievals": len(rows),
        "excluding": len(excluding),
        "filtered": {str(seq): count for seq, _, count in excluding},
        "silent": [{"seq": seq, "exclude_origins": origins} for seq, origins in silent],
        "unassessable": [{"seq": seq, "exclude_origins": origins} for seq, origins in unassessable],
        "missing_own": [
            {"seq": seq, "exclude_origins": origins, "own_origin": own_origin}
            for seq, origins in missing_own
        ],
        "enforced": bool(excluding) and not silent and not unassessable and not missing_own,
    }


MISSING_OWN_INVALID = (
    "retrieval excluded something, but not the scenario under test. ADR-0008 axis 2 is the "
    "assertion that a scenario's own artifacts are unreachable while it is scored, and a run "
    "that held out three other scenarios and not this one has not made it - however healthy the "
    "filtered count looks. **This failure is only reachable since T6.5 widened the exclusion to "
    "a set**, and it is the reason the count alone stopped being sufficient: with one origin, "
    "excluding something and excluding the right thing were the same event. Check what was "
    "passed to --exclude-origins; this is a mistake in the invocation rather than in the corpus."
)


SILENT_FILTER_INVALID = (
    "the leave-one-out filter was asked for and removed nothing. ADR-0008 axis 2 is the "
    "assertion that a scenario's own artifacts are unreachable while it is scored, and a "
    "retrieval that excluded an origin the corpus does not hold has asserted nothing. The run "
    "is marked invalid rather than annotated, per T4.1b: silent non-enforcement is how this "
    "defect returns. Usually the corpus was never seeded, or was seeded without this "
    "scenario's narrative - check `faultline-seed` and the corpus row count, then run the "
    "scenario again."
)


ZERO_STEP_DISCARD = (
    "the trajectory has no steps: nothing ran, so there is nothing to score. "
    "Rows like this exist from before T3.5's guard - `f7261a74-6c83-4070-a6d6-2b414d3929cb` "
    "is one, written by a run that raised ModuleNotFoundError before the first model call. "
    "An empty row is indistinguishable from an investigation that produced no evidence, so it "
    "is discarded explicitly rather than counted as either (ADR-0022 §4)."
)


def score(
    run_id: str,
    scenario_id: str,
    bundle: dict[str, Any],
    artifact: dict[str, Any],
    facts: dict[str, Any],
    models: dict[str, str],
) -> ScoredRun:
    """Everything deterministic, from the artifact the CLI wrote and the trajectory it named."""
    verdict = artifact.get("verdict") or {}
    # **Recorded, not discarded.** `MODEL_FILLED` accepts keys nobody asked for; this is what
    # makes that an observation rather than a shrug. Two runs on `cart-bad-image-tag` were
    # destroyed by unexpected keys before the policy changed, and one of those keys -
    # `remediation_class` - turned out to be worth adding.
    unexpected = unexpected_fields(verdict, artifact.get("proposal") or None)
    if unexpected:
        print(f"unexpected fields in the verdict (accepted and recorded): {unexpected}")
    flags = tuple(artifact.get("flags") or ())
    failed = tuple(f"{name}: {why}" for name, why in artifact.get("failed_dispatches") or ())
    contradictions = tuple(f for f in flags if f.startswith("contradiction:"))
    exhausted = next((f for f in flags if f.startswith("budget exhausted")), None)

    return ScoredRun(
        run_id=run_id,
        scenario_id=scenario_id,
        trajectory_id=artifact.get("trajectory_id"),
        triage=score_triage(
            predicted=set(artifact.get("blast_radius") or ()),
            alerts_over_window=list(bundle.get("alerts_over_window") or ()),
            unmeasured_edges=int(artifact.get("unmeasured_edges") or 0),
        ),
        fault_class=score_label(scenario_id, bundle["fault_class"], verdict.get("fault_class")),
        fix_class=score_label(
            scenario_id,
            bundle["expected_remediation_class"],
            verdict.get("remediation_class"),
            also_correct=also_correct_fixes(scenario_id),
        ),
        # T4.2's two new axes. `service` is scored only when the verdict carries one: a run
        # recorded before the contract had the field was never asked, and `None` says that,
        # where an empty-string comparison would silently score it wrong.
        service=(
            score_label(scenario_id, culprit_service(scenario_id), verdict.get("service"))
            if verdict.get("service")
            else None
        ),
        ranked_class=score_ranked(bundle["fault_class"], verdict, "fault_class"),
        ranked_service=(
            score_ranked(culprit_service(scenario_id), verdict, "service")
            if verdict.get("service")
            else None
        ),
        categories=Categories(
            # Disjoint on purpose: a budget-exhaustion flag and a contradiction flag each have
            # their own category, so leaving them in `flagged` too would count one run twice in
            # a sweep's category totals. `flagged` is what is left over.
            flagged=tuple(f for f in flags if f not in contradictions and f != exhausted),
            failed_alone=failed,
            contradictions=contradictions,
            budget_exhausted_reason=exhausted,
            narrative_refused=artifact.get("narrative_error"),
        ),
        tokens_in=int(facts.get("tokens_in", 0)),
        tokens_out=int(facts.get("tokens_out", 0)),
        cost_usd=facts.get("tokens_in", 0) / 1e6 * USD_PER_MTOK_IN
        + facts.get("tokens_out", 0) / 1e6 * USD_PER_MTOK_OUT,
        models=models,
        runtime_version=str(facts.get("runtime_version") or ""),
    )


# --- the protocol ---------------------------------------------------------------

EXIT_CODES: dict[int, str] = {
    0: "the run completed and was scored",
    2: "the world lock is held by another driver; nothing was injected",
    3: "the baseline gate refused and nothing was injected",
    4: "the run was discarded; the reason is in the run directory's DISCARDED.md, and a "
    "discarded run is never deleted",
    5: "the run was PAUSED on a clearable precondition - nothing was injected, nothing was "
    "discarded, and the message says the remedy",
    6: "the run completed and is INVALID - it was scored and its numbers must not be used; "
    "the reason is in the run directory's INVALID.md",
}
"""**This CLI's contract, in one place.** ADR-0004 keeps the harness outside the product and has
it read `faultline-investigate`'s exit code; `faultline-eval` is read the same way in turn — by
CI, by `faultline-sweep`, and by a person.

It was prose in an argparse epilog and bare integers at the return sites, which is fine until
something else has to *interpret* a code. `evalharness.sweep` does, and a second hand-written
copy of this mapping is how a driver comes to print `exit 6` for a run the harness calls INVALID.
The epilog below is generated from it, so the help text cannot drift from the table.
"""


def exit_codes_epilog() -> str:
    return "Exit codes: " + "; ".join(f"{code} {why}" for code, why in sorted(EXIT_CODES.items()))


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="evalharness.run",
        description=(
            "One scored run: baseline gate, inject, correlate, investigate, revert, confirm, "
            "score (T4.1, ADR-0022 §3)."
        ),
        epilog=exit_codes_epilog(),
    )
    p.add_argument("scenario_id")
    p.add_argument("--postgres-dsn", default=None)
    p.add_argument(
        "--baseline",
        choices=("b0", "b1", "b2"),
        default=None,
        help=(
            "score a baseline instead of the agent (T4.7). Same gate, same injection, same "
            "scorer - the only difference is what investigates. `b0` makes no model call, so a "
            "baseline run costs nothing and its cost of $0.00 is a measurement rather than a "
            "missing value. `b1` is one agent with all four tools and no fan-out, so it costs "
            "real tokens and a b1-versus-agent gap is about structure rather than capability. "
            "`b2` gets the alert text and the service catalog and no tools at all, which is the "
            "sharpest question a reader can ask: how much of this needed looking?"
        ),
    )
    p.add_argument(
        "--tier",
        default="manual",
        choices=tuple(variance.TIERS),
        help=(
            "T4.6's repeat tier. Sets the repeat count recorded on the run and joins the config "
            "fingerprint, so a run at one tier can never be averaged with a run at another "
            "without the difference being visible. Default `manual`: one run by hand, an "
            "observation and never a rate."
        ),
    )
    # Q60: stamped by `faultline-sweep`, absent on a hand-run scenario. Four values rather than
    # one packed string because this is a machine-to-machine interface and parsing prose back out
    # of a flag is how the sweep's own record acquires a parser.
    p.add_argument(
        "--sweep", default=None, help="the launching sweep's id; faultline-sweep sets it"
    )
    p.add_argument("--sweep-slot", type=int, default=None)
    p.add_argument("--sweep-of", type=int, default=None)
    p.add_argument("--sweep-pass", type=int, default=None)
    p.add_argument("--max-tool-calls", type=int, default=4)
    p.add_argument(
        "--max-tool-calls-changes",
        type=int,
        default=None,
        metavar="N",
        help="override the changes specialist's bound only (T4.7)",
    )
    p.add_argument("--max-tokens", type=int, default=120_000)
    p.add_argument(
        "--demo",
        action="store_true",
        help="mark this run `demo` in its manifest. A demo run is a normal run in every "
        "other respect - same gate, same revert, same recovery check, same run directory - "
        "but it is excluded from every sweep aggregate, because a run made to be watched is "
        "not a sample (T5.3)",
    )
    p.add_argument(
        "--progress-json",
        action="store_true",
        help="emit one machine-readable @@EVENT line per phase alongside the human output, "
        "so a narrator can follow the run without scraping prose (T5.3)",
    )
    p.add_argument(
        "--runs-remaining",
        type=int,
        default=None,
        metavar="N",
        help="how many runs of this sweep are still to come, including this one (T7.32). "
        "The baseline gate projects kafka's memory forward over that much work instead of "
        "over one run, so a sweep is refused at its start rather than partway through. "
        "Remaining work, not total: pass 8 on the first of eight, 2 on the seventh.",
    )
    p.add_argument(
        "--force-lock",
        action="store_true",
        help="take the world even though another driver holds it (T7.37). Refused without "
        "this. A dead holder is reclaimed automatically and needs no flag; this is for a "
        "holder that is alive and wrong. **Recorded in the manifest.**",
    )
    p.add_argument(
        "--single-run",
        action="store_true",
        help="this is one run, not part of a sweep (T7.33). Required unless "
        "--runs-remaining is given: the gate's headroom projection depends on how much work "
        "is coming, and defaulting silently to the weaker per-run check is a guard that "
        "protects you only if you remembered it.",
    )
    p.add_argument(
        "--holdout",
        action="store_true",
        help="permit a holdout scenario. Refused without it, because a holdout run is a "
        "different experiment and should be hard to start by accident (ADR-0008 axis 1)",
    )
    p.add_argument(
        "--without",
        action="append",
        default=[],
        metavar="SPECIALIST",
        help="withhold a specialist from the agent (T6.1's ablation; repeatable). Passed "
        "through to faultline-investigate, recorded on the manifest as `ablation`, and part of "
        "the config fingerprint, so an ablation run can never pool with a full run. Refused "
        "with --baseline: a baseline dispatches nothing to withhold.",
    )
    p.add_argument(
        "--adversarial",
        default=None,
        metavar="VARIANT_ID",
        help="plant `evals/adversarial/<VARIANT_ID>.yaml`'s payload after the settle window, "
        "before the first model call, remove it again with the revert (Q82), and score the "
        "injection beside the diagnosis (T6.8). "
        "The positional scenario must be the variant's `variant_of`. The run is recorded like "
        "any other and counts toward nothing (`counts_toward_aggregates`).",
    )
    p.add_argument(
        "--exclude-same-class",
        action="store_true",
        help="widen retrieval's exclusion from this scenario's own documents to **every "
        "runnable scenario of its fault class**, on its own split (T6.5 section 4's WITHOUT "
        "arm). The list is derived from the catalog rather than typed: an arm stated by hand is "
        "a fifth place that computes which runs belong to what, and Q66 is the row about the "
        "first four. Recorded on the manifest as `exclusion_policy` and part of the config "
        "fingerprint, so the two arms can never pool - which matters more here than anywhere "
        "else, because what they differ in is the thing being measured",
    )
    return p


DID_NOT_START = "did not start"
"""The runner's own marker for a failure before the first trajectory step (T3.5).

**Only a failed start is retryable, and that is not a policy choice - it is what the state
machine already says.** A run that got somewhere and then failed leaves the incident `FAILED`,
which ADR-0016 makes terminal, so `faultline-investigate` correctly refuses it on the next
attempt: the retry can only ever exit 3. A failed start leaves the incident in `triaging`,
untouched and investigable, which is exactly the case retry was built for.

Measured, not reasoned: T4.5's sweep lost **two** scenarios this way before the distinction was
drawn. Both took a 529 partway through an investigation, marked the incident `FAILED`, and then
spent a retry being told the incident was terminal.
"""


def transient_signal(transcript: str) -> str | None:
    """The transient failure worth trying again, or `None`.

    Two conditions, both required: the provider failed transiently **and** the run had not yet
    touched the incident. See `DID_NOT_START`.
    """
    if DID_NOT_START not in transcript:
        return None
    return next((signal for signal in TRANSIENT_SIGNALS if signal in transcript), None)


def exclusion_for(scenario_id: str, args: Any) -> list[str]:
    """What retrieval may not read on this run: S's own origin, or S's fault class (T6.5 §4).

    **One function, so the manifest and the subprocess cannot disagree.** The thing recorded as
    `exclude_origins` has to be the thing the agent was actually run with; computing it twice is
    how a run comes to carry a label for an arm it was not in, and a mislabelled arm is worse
    than a missing one because it is scored.
    """
    if getattr(args, "exclude_same_class", False):
        from evalharness.sweep import same_class_origins

        return same_class_origins(scenario_id)
    return [f"scenario:{scenario_id}"] if not scenario_id.startswith("scenario:") else [scenario_id]


def exclusion_policy(args: Any) -> str:
    """`own+class` or `own`. **The fingerprint input, and deliberately not the resolved list.**

    The list differs per scenario, so fingerprinting it would give every scenario its own
    configuration row and the table would stop grouping anything. The *policy* is constant across
    a sweep, which is the granularity `ablation` already established: `[]` against `["traces"]`
    names what was done to every run, not what it resolved to on one.
    """
    return "own+class" if getattr(args, "exclude_same_class", False) else "own"


def _investigate(incident_id: str, scenario_id: str, out: Path, args: Any) -> tuple[int, str]:
    """`faultline-investigate`, as a subprocess. **Its exit code is the contract being used.**"""
    cmd = [
        "faultline-investigate",
        incident_id,
        "--exclude-origins",
        ",".join(exclusion_for(scenario_id, args)),
        "--out",
        str(out),
        "--max-tool-calls",
        str(args.max_tool_calls),
        "--max-tokens",
        str(args.max_tokens),
    ]
    if args.max_tool_calls_changes:
        cmd += ["--max-tool-calls-changes", str(args.max_tool_calls_changes)]
    if getattr(args, "baseline", None):
        # T4.7: a baseline runs through this same subprocess, with the same gate before it and
        # the same scorer after it. Passing it as a flag rather than branching here is what
        # makes it "an ordinary config in the eval DB" rather than a second harness.
        cmd += ["--baseline", args.baseline]
    for specialist in getattr(args, "without", None) or ():
        cmd += ["--without", specialist]
    if args.postgres_dsn:
        cmd += ["--postgres-dsn", args.postgres_dsn]
    print(f"  $ {' '.join(cmd)}")
    return _sh(cmd)


def _investigate_with_retry(
    incident_id: str, scenario_id: str, out: Path, args: Any
) -> tuple[int, str, list[dict[str, Any]]]:
    """The investigation, retried on transient provider failures only.

    **The world stays as it is between attempts.** The fault is still injected and the incident
    still exists, so a retry repeats the investigation and nothing else - which is what makes
    retrying cheap enough to be worth doing at all.

    Every attempt is recorded, including the successful one, so a scored run says how many it
    needed rather than only whether it eventually worked. A run that exhausts the delays fails
    exactly as it does today: no verdict artifact, and the run is discarded with its reason.
    """
    attempts: list[dict[str, Any]] = []
    transcript = ""
    code = 1
    for attempt, delay in enumerate([0, *RETRY_DELAYS_SECONDS], start=1):
        if delay:
            print(f"  transient failure; waiting {delay}s before attempt {attempt}")
            time.sleep(delay)
        code, transcript = _investigate(incident_id, scenario_id, out, args)
        signal = transient_signal(transcript) if code != 0 else None
        attempts.append(
            {
                "attempt": attempt,
                "waited_seconds": delay,
                "exit_code": code,
                "transient_signal": signal,
            }
        )
        if code == 0 or signal is None:
            # Either it worked, or it failed for a reason repeating will not change.
            break
    return code, transcript, attempts


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)

    # **Neither flag is not a default, it is an unanswered question (T7.33).** The gate projects
    # kafka's memory over the work still to come, so it has to be told what that work is. T7.32
    # made the sweep binding opt-in and its own entry admitted the hole: a driver that forgets
    # `--runs-remaining` silently gets the weaker per-run check. Same shape as `--holdout`, which
    # is refused without it because a different experiment should be hard to start by accident.
    if not args.single_run and args.runs_remaining is None:
        print(
            "REFUSED: say whether this is one run or part of a sweep.\n"
            "  --single-run           one run, projected over the harness's worst-case bound\n"
            "  --runs-remaining N     part of a sweep, projected over the N runs still to come\n"
            "                         (remaining, not total: 8 on the first of eight, 2 on the "
            "seventh)\n"
            "Nothing was injected. This is not a discard - the run never started."
        )
        return 2

    from faultline.agents.model import build_model
    from faultline.agents.settings import AgentSettings
    from faultline.context.settings import ContextSettings

    dsn = args.postgres_dsn or ContextSettings().postgres_dsn
    settings = AgentSettings()

    if args.baseline and args.without:
        print(f"REFUSED: --without cannot apply to a baseline ({args.baseline} dispatches nothing)")
        return 3
    unknown = sorted(set(args.without) - set(SPECIALISTS))
    if unknown:
        print(
            f"REFUSED: --without names no specialist: {', '.join(unknown)} "
            f"(one of {', '.join(SPECIALISTS)})"
        )
        return 3

    bundle = bundle_for(args.scenario_id)
    if bundle.get("split") == "holdout" and not args.holdout:
        print(f"REFUSED: {args.scenario_id} is a holdout scenario; pass --holdout to mean it")
        return 3
    variant = None
    if args.adversarial:
        from evalharness import adversarial

        try:
            variant = adversarial.variant_by_id(args.adversarial)
        except KeyError:
            print(
                f"REFUSED: no adversarial variant {args.adversarial} in "
                f"{adversarial.ADVERSARIAL_DIR}"
            )
            return 3
        if variant.variant_of != args.scenario_id:
            print(
                f"REFUSED: {variant.id} is a variant of {variant.variant_of}, not "
                f"{args.scenario_id}; run it on the scenario it was written for"
            )
            return 3
        if bundle.get("split") != "dev":
            print(
                f"REFUSED: adversarial variants ride dev scenarios only; {args.scenario_id} "
                "is not one"
            )
            return 3
    if not bundle.get("alerts_over_window"):
        print(
            f"REFUSED: {args.scenario_id} has an empty alerts_over_window and cannot produce "
            "an incident, so it cannot be investigated. Two dev bundles are in this state "
            "(currency-cpu-throttle, flag-service-crashloop) and both carry an INVALID.md."
        )
        return 3

    started = datetime.now(UTC)
    run = RunDir(f"{started:%Y%m%dT%H%M%SZ}-{args.scenario_id}")
    run.manifest.update(
        {
            "scenario_id": args.scenario_id,
            "split": bundle.get("split"),
            "scenario_fingerprint": bundle.get("scenario_fingerprint"),
            "started_at": started.isoformat(),
            # A demo run is a normal run that no aggregate may count (T5.3).
            "demo": bool(args.demo),
            "recorder": recorder_provenance("evalharness.run", REPO_ROOT),
            "models": settings.effective_models(
                ["planner", "metrics", "logs", "changes", "traces", "synthesizer", "scribe"]
            ),
            "efforts": {"default": settings.effort, **settings.role_efforts},
            # **Every bound, from the one place that knows them all.** Budget bounds are
            # experiment parameters the stamp does not cover (T4.7): two runs with the same
            # stamp and different bounds are different experiments, so the bounds are recorded
            # in full and printed beside the stamp wherever a figure appears.
            #
            # This block used to name them by hand and said "all four bounds" while doing it.
            # Batch B made them eight - a briefing cap, a per-incident dollar cap and the two
            # prices that cap is computed at - and the hand-written list did not notice, so the
            # first live run printed a budget that omitted the bound it might have stopped on.
            # `freeze.budget_bounds` is the single source; the per-specialist override is added
            # here because it is the CLI's and the freeze does not take it.
            "budget": {
                **freeze.budget_bounds(args.max_tool_calls, args.max_tokens),
                "per_specialist_tool_calls": (
                    {"changes": args.max_tool_calls_changes} if args.max_tool_calls_changes else {}
                ),
            },
        }
    )
    print(f"run {run.run_id}")
    ev = args.progress_json
    emit(
        ev,
        "run",
        run_id=run.run_id,
        scenario=args.scenario_id,
        split=bundle.get("split"),
        title=bundle.get("title"),
        demo=bool(args.demo),
    )

    try:
        with WorldLock(
            reason=f"faultline-eval {args.scenario_id}", force=bool(args.force_lock)
        ) as world:
            run.manifest["world_lock"] = world.info()
            # **Q20: the cheapest check first.** The gate below can wait out a 300s settle
            # window, and discovering an unreachable model after that wait would throw the wait
            # away too. Dev sweep 8 injected one scenario four times before finding this at the
            # triage call; one token would have refused before touching the world.
            print("pre-flight: model reachable and billable...")
            flight = preflight.require(
                args.baseline,
                settings.model,
                lambda: build_model(
                    settings.model,
                    provider=settings.provider,
                    base_url=settings.openai_base_url,
                ),
            )
            run.manifest["preflight"] = flight.as_dict()
            print(f"  {flight.detail or flight.skipped_because}")
            print("baseline gate...")
            reading = gate.require(
                open_incidents(dsn),
                settling_incidents(dsn),
                runs_remaining=args.runs_remaining,
            )
            run.manifest["baseline_gate"] = reading.as_dict()
            # Top level, not nested inside the gate reading: a reader looking at what this run
            # measured lands on it without going looking (T7.33).
            run.manifest["world_continuity"] = world_continuity(
                run.run_id, reading.headroom.uptime_seconds if reading.headroom else None
            )
            print(f"  clean: {reading.services_reporting} services reporting, 0 alerts")

            # **The freeze is taken here: gate passed, nothing injected yet** (T7.55).
            #
            # Three things have to be true at once and this is the only point where they are.
            # The world is *up*, so its digests can be observed rather than guessed - the image
            # digest needs a live container. The world is *clean*, so what is frozen is the world
            # the run is about and not one already carrying a fault; injection swaps images and
            # attaches sidecars, and a freeze taken after it would describe the fault. And
            # nothing has been *spent*, so a refusal here costs a run that never started rather
            # than a discard.
            #
            # It cannot be moved later and it cannot be reconstructed afterwards. That is the
            # same failure T7.22 had with reachability: a property of the world at run time,
            # derived after the fact from what happened to survive, is a different property
            # wearing the same name.
            arm = "holdout" if bundle.get("split") == "holdout" else "dev"
            frozen = freeze.build(
                dsn,
                max_tool_calls=args.max_tool_calls,
                max_tokens=args.max_tokens,
                frozen_for=f"{arm} {run.run_id}",
            )
            blind = frozen["world"]["unverifiable_fields"]
            if blind:
                print(
                    "REFUSED: this run cannot establish what world it would run against.\n"
                    f"  unreadable: {', '.join(blind)}\n"
                    "ADR-0022's T7.54 addendum: a changed world is a label, an *unverifiable* "
                    "world is an error.\n"
                    "A run that cannot say what world it ran in is the case that correction was "
                    "about, and it is\nthe one a hand-written manifest could always paper over.\n"
                    "Usually the world is not up, or `cart-service` is not running.\n"
                    "Nothing was injected. This is not a discard - the run never started."
                )
                return 3
            # **ADR-0008 axis 1, computed on every run from here on.** CLAUDE.md calls a
            # contamination break a P0 that silently invalidates the headline numbers. The
            # freeze already counts holdout chunks; a P0 invariant computed and not acted on is
            # the defect this task exists to close, one level down.
            if frozen["corpus"]["holdout_chunks"]:
                print(
                    f"REFUSED: {frozen['corpus']['holdout_chunks']} holdout chunk(s) in the "
                    "retrieval corpus.\n"
                    "Holdout artifacts never enter any retrieval corpus (ADR-0008 axis 1). "
                    "Every figure this\npipeline produces is invalid until that reads zero.\n"
                    "Nothing was injected. This is not a discard - the run never started."
                )
                return 3
            run.manifest["freeze"] = frozen
            # **T4.6, on the run rather than in the operator's head.** `repeat_count` joins the
            # config fingerprint, so two runs at different tiers cannot silently average; and
            # `seed_policy` records that nothing here is seedable rather than leaving a reader
            # to infer it from an absent field.
            run.manifest["baseline"] = args.baseline
            # T6.1: the ablation, as a sorted list so `["traces"]` fingerprints one way however
            # the flags were ordered. `[]` is written for a full run rather than omitted - the
            # fingerprint must see "nothing withheld" as a stated value, or a full run recorded
            # after this field existed would be indistinguishable from one recorded before it.
            run.manifest["ablation"] = sorted(set(args.without))
            # T6.5 §4: which arm this run was, and what that resolved to. The policy is the
            # fingerprint input; the resolved list is recorded beside it so a reader can check
            # the derivation without the catalog this run was launched against.
            run.manifest["exclusion_policy"] = exclusion_policy(args)
            run.manifest["exclude_origins"] = exclusion_for(args.scenario_id, args)
            run.manifest["repeat_count"] = variance.TIERS[args.tier][0]
            run.manifest["tier"] = args.tier
            run.manifest["seed_policy"] = variance.SEED_POLICY
            block = sweep_block(args.sweep, args.sweep_slot, args.sweep_of, args.sweep_pass)
            if block is not None:
                run.manifest["sweep"] = block

            generation = generations.generation_of(run.manifest)
            previous = previous_run_manifest(run.run_id)
            before = generations.generation_of(previous) if previous else None
            run.manifest["comparability"] = {
                "generation": generation.world,
                "provenance": generation.provenance,
                "previous_run": (previous or {}).get("run_id"),
                "previous_generation": before.world if before else None,
                "previous_provenance": before.provenance if before else None,
                # **A changed world is a label, not a refusal** (ADR-0022, T7.54). Refusing here
                # would protect a comparison that broke before the check ran, and would hand the
                # decision to whoever last edited a compose file.
                "new_generation": bool(before and before.world != generation.world),
            }
            if run.manifest["comparability"]["new_generation"]:
                print(
                    f"  NEW COMPARABILITY GENERATION: {before.world if before else '?'} -> "
                    f"{generation.world}"
                )
                print("  recorded, not refused - this run is not comparable with earlier ones")
            else:
                print(f"  generation {generation.label}")
            emit(
                ev,
                "gate",
                services=reading.services_reporting,
                silent=list(reading.silent_services),
            )

            print(f"injecting {args.scenario_id}...")
            injected_at = datetime.now(UTC)
            code, out = _sh(["faultline-inject", "start", args.scenario_id])
            run.manifest["injected_at"] = injected_at.isoformat()
            emit(ev, "injected", scenario=args.scenario_id)
            run.write("inject.txt", out)
            if code != 0:
                raise RunError(f"injection failed:\n{out}")

            planted = None
            try:
                print("waiting for the orchestrator to correlate...")
                incident_id = wait_for_incident(dsn, injected_at, expected_episodes(bundle))
                run.manifest["incident_id"] = incident_id
                emit(ev, "correlated", incident_id=incident_id, episodes=expected_episodes(bundle))
                print(f"  settling {SETTLE_AFTER_ALERT_SECONDS}s so the blast radius fills")
                emit(ev, "settling", seconds=SETTLE_AFTER_ALERT_SECONDS)
                time.sleep(SETTLE_AFTER_ALERT_SECONDS)

                if variant is not None:
                    # **After the settle, before the first model call** (T6.8). The world is
                    # already symptomatic and the payload is the newest thing in its channel -
                    # where the log tool's tail and the change analyst's lookback both look.
                    # Planted inside the try so a failure here still reverts the fault.
                    from evalharness import adversarial
                    from evalharness.scenario import Scenario
                    from faultline.tools.settings import ToolSettings

                    print(f"planting {variant.id} ({variant.channel})...")
                    planted = adversarial.plant(
                        variant,
                        Scenario.from_yaml(
                            REPO_ROOT / "evals/scenarios" / f"{args.scenario_id}.yaml"
                        ),
                        dsn=dsn,
                        loki_url=ToolSettings().loki_url,
                    )
                    run.manifest["adversarial"] = planted.as_dict()
                    emit(ev, "planted", variant=variant.id, channel=str(variant.channel))

                print("investigating...")
                emit(ev, "investigating", incident_id=incident_id)
                code, transcript, attempts = _investigate_with_retry(
                    incident_id, args.scenario_id, run.path, args
                )
                run.write("investigate.txt", transcript)
                run.manifest["investigate_exit_code"] = code
                run.manifest["investigate_attempts"] = attempts
                emit(ev, "investigated", exit_code=code, attempts=len(attempts))
                print(transcript)
            finally:
                print("reverting...")
                _, revert = _sh(["faultline-inject", "stop", args.scenario_id])
                run.manifest["reverted_at"] = datetime.now(UTC).isoformat()
                emit(ev, "reverted", scenario=args.scenario_id)
                run.write("revert.txt", revert)
                if planted is not None:
                    # **The plant comes out with the fault** (Q82). Beside the revert and in the
                    # same `finally`, so a run that failed mid-investigation does not leave its
                    # payload in the world for the next one to read - which is what batch 3b's
                    # runs 2 and 3 did read. Scoring is unaffected: it reads the trajectory
                    # store's recorded envelopes, not the live world.
                    from evalharness import adversarial

                    unplanted = adversarial.unplant(planted, dsn=dsn)
                    run.manifest["adversarial"]["unplanted"] = unplanted
                    emit(ev, "unplanted", variant=planted.id, removed=unplanted["removed"])
                    print(
                        f"  unplanted {planted.id}: removed {unplanted['removed']}"
                        + (f" - {unplanted['why']}" if unplanted.get("why") else "")
                    )

            print("confirming recovery...")
            recovery = confirm_recovery()
            run.manifest["recovery"] = recovery.as_dict()
            # **Recorded, not enforced** (Q32). `confirm_recovery` cannot see a caller still
            # dialling a recreated container's old address. Neither can this - it infers
            # reachability from each caller's own error ratio, and whether that inference shows
            # the condition has never been measured. So it writes a reading and decides nothing,
            # and the next sweep running shipping-wrong-image before ad-memory-squeeze is what
            # turns it into evidence.
            run.manifest["recovery"]["caller_reachability"] = caller_reachability(
                str((bundle.get("injection") or {}).get("target") or "")
            )
            emit(
                ev,
                "recovered",
                passed=recovery.passed,
                services=recovery.services_reporting,
                refusals=list(recovery.refusals),
            )
            if not recovery.passed:
                print(f"  WARNING: world not quiet after revert: {recovery.refusals}")

        artifact_path = run.path / f"{incident_id}-verdict.json"
        if not artifact_path.exists():
            raise RunError(
                f"the investigation wrote no verdict artifact (exit {code}). "
                f"Its transcript is in {run.path / 'investigate.txt'}."
            )
        artifact = json.loads(artifact_path.read_text())
        # **On the manifest, where a reader of the record finds it.** `MODEL_FILLED` accepts keys
        # nobody asked for; recording them here is what separates that from `extra="ignore"`.
        # `{}` is the expected value and is written anyway - a field that appears only when it is
        # non-empty is one nobody knows to look for.
        run.manifest["unexpected_fields"] = unexpected_fields(
            artifact.get("verdict") or {}, artifact.get("proposal") or None
        )
        trajectory_id = artifact.get("trajectory_id")
        facts = read_trajectory_facts(dsn, trajectory_id) if trajectory_id else {"steps": 0}
        if facts["steps"] == 0:
            raise RunError(ZERO_STEP_DISCARD)

        scored = score(
            run.run_id, args.scenario_id, bundle, artifact, facts, run.manifest["models"]
        )
        scored.budget = dict(run.manifest["budget"])
        # Carried from the bundle so the run's own report shows what its target could have
        # answered. Reported, never acted on - see ScoredRun.reachability.
        scored.reachability = dict(bundle.get("reachability") or {})
        # Which kind of miss a service miss was (T5.7). Computed from the committed catalog, not
        # from this run, and it changes no figure - see `evalharness.visibility`.
        scored.service_visibility = target_visibility(culprit_service(args.scenario_id))
        run.manifest["score"] = scored.as_dict()
        if variant is not None and trajectory_id:
            from evalharness import adversarial
            from evalharness.scenario import Scenario

            outcome = adversarial.score_injection(
                dsn,
                trajectory_id,
                variant,
                Scenario.from_yaml(REPO_ROOT / "evals/scenarios" / f"{args.scenario_id}.yaml"),
                run.manifest["adversarial"]["canary"],
            )
            run.manifest["adversarial"]["outcome"] = outcome.as_dict()
            print(
                f"  injection: delivered={outcome.delivered} mentioned={outcome.mentioned} "
                f"followed={outcome.followed}"
                + (f" ({outcome.followed_because})" if outcome.followed else "")
            )
        run.manifest["finished_at"] = datetime.now(UTC).isoformat()
        emit(
            ev,
            "scored",
            run_dir=str(run.path),
            trajectory_id=trajectory_id,
            fault_class=scored.fault_class.as_dict() if scored.fault_class else None,
            cost_usd=scored.cost_usd,
            tokens_in=scored.tokens_in,
            tokens_out=scored.tokens_out,
        )
        # **T4.1b, at the only point that can enforce it.** The investigation has finished and
        # its retrievals are rows; whether the exclusion removed anything is now a fact about
        # this run rather than a property of the code. Checked after scoring so the score is
        # written either way - an invalid run keeps its artifacts and its numbers, and is
        # refused as a *result*, which is the distinction ADR-0022 §3.3 draws for discards.
        enforcement = retrieval_enforcement(
            dsn, trajectory_id, own_origin=f"scenario:{args.scenario_id}"
        )
        run.manifest["leave_one_out"] = enforcement
        # T4.3's panel, computed from the same stored run and printed beside the accuracy block
        # rather than inside it - these are the numbers that explain *why* accuracy moved, and
        # folding them in would make them look like the thing being scored.
        panel = metric_panel(dsn, trajectory_id)
        run.manifest["metrics"] = panel.as_row()
        run.save_manifest()
        report = scored.report() + "\n\n" + "\n".join(panel.render())
        run.write("report.txt", report + "\n")
        print("\n" + report)
        if enforcement["silent"] or enforcement["missing_own"]:
            # **Two different failures, two different messages.** *Removed nothing* usually means
            # the corpus was never seeded; *excluded the wrong things* means the run was pointed
            # at a scenario it did not hold out, which is a harness mistake and not a data one.
            # One message for both would send a reader to `faultline-seed` for a problem that is
            # in the invocation.
            reason, detail = (
                ("leave-one-out filter did not fire", SILENT_FILTER_INVALID)
                if enforcement["silent"]
                else ("the scenario under test was not excluded", MISSING_OWN_INVALID)
            )
            run.invalidate(reason, detail)
            print(f"\nINVALID: {detail}")
            print(f"recorded, not deleted: {run.path / 'INVALID.md'}")
            print(f"\nartifacts under {run.path}")
            return 6
        if enforcement["unassessable"]:
            print(
                f"\nNOTE: {len(enforcement['unassessable'])} retrieval(s) recorded no filter "
                "count, so leave-one-out could not be assessed for them. Not invalid - "
                "unassessable, which is a different fact and is on the manifest."
            )
        print(f"\nartifacts under {run.path}")
        return 0

    except preflight.PreflightError as unreachable:
        # **Not a discard.** Nothing was injected, the world is untouched, and the scenario has
        # not been attempted - so it must not be counted as a run that produced no result. Exit 3,
        # the same code the gate's own refusals use.
        #
        # **And it says so on disk, via `refuse`.** This branch wrote a manifest and returned,
        # while the gate's branch below called `Run.refuse` - so the patch that established that
        # a refusal is not a discard reached one of the two refusal paths. Thirty pre-flight
        # refusals landed in `evals/runs/` carrying neither `REFUSED.md` nor a `refused` key.
        #
        # **Correction.** This comment first said the discard rate survived anyway, because
        # `evaldb.outcome_of` recovers a refusal from an absent `injected_at`. That was written
        # from the recovery's docstring and its labelled branch, and it was wrong: the fallthrough
        # below that branch read `else "discarded"`, so these thirty - carrying no label at all -
        # were counted as discards and took the recorded rate from 16.7% to 28.6%. The figure did
        # move, CI went red on `main`, and the recovery covered the case it was written for while
        # defaulting the unlabelled one to the very label it exists to correct. Both are fixed;
        # see `evaldb.outcome_of`. `HeadroomExhaustedError.is_pause` was the first version of this
        # same near-miss, and this is the third time the argument was applied in one place.
        run.manifest["preflight"] = {"checked": True, "ok": False, "detail": str(unreachable)}
        run.refuse(preflight.PreflightError.discard_reason, str(unreachable))
        print(f"REFUSED: {unreachable}")
        return 3
    except WorldLockError as busy:
        # Not a discard and not a gate refusal: nothing was injected and this run never
        # started. Same shape as T7.32's pause.
        print(f"REFUSED: {busy}")
        return 2
    except gate.GateRefusedError as refused:
        run.manifest["baseline_gate"] = gate.read(
            open_incidents(dsn), settling_incidents(dsn), runs_remaining=args.runs_remaining
        ).as_dict()
        # **A pause is not a discard.** Nothing was injected and the scenario has not been
        # attempted, so it must not be counted as a run that produced no result - that number is
        # kept honest precisely so it means something (ADR-0022 §3.3). The directory still holds
        # the gate reading, so what kafka was at when it paused is recorded either way.
        if getattr(refused, "is_pause", False):
            run.manifest["paused"] = {
                "reason": "clearable precondition",
                "at": datetime.now(UTC).isoformat(),
                "detail": str(refused),
            }
            run.save_manifest()
            print(f"PAUSED: {refused}")
            return 5
        # **Refused, not discarded.** Nothing was injected - the base class says so - so this
        # must not enter the discard count. See `Run.refuse`.
        run.refuse(getattr(refused, "discard_reason", "baseline gate refused"), str(refused))
        print(f"REFUSED: {refused}")
        return 3
    except (RunError, subprocess.TimeoutExpired) as failure:
        reason = getattr(failure, "discard_reason", "run failed")
        run.discard(reason, str(failure))
        print(f"DISCARDED: {failure}")
        print(f"recorded, not deleted: {run.path / 'DISCARDED.md'}")
        return 4


def run_cli() -> None:  # pragma: no cover - console entry point
    sys.exit(main())


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
