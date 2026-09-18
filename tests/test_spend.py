"""Q70: the sweep reads what it has spent and stops at the ceiling it was given.

Every registered hard ceiling before this was enforced by an operator watching. T6.5 §6 wrote
*"Reaching it stops the run where it stands and reports the arms it did not complete"* about a
harness that could do neither; Amendment 7 §4 did it by hand at block boundaries. These tests are
that sentence made true.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from evalharness import spend, sweep


def _manifest(
    root: Path, name: str, *, session: str | None, incident: str | None, cost: float | None
) -> None:
    run = root / name
    run.mkdir()
    body: dict[str, Any] = {"run_id": name}
    if session:
        body["sweep"] = {"id": session, "slot": 1, "of": 3, "pass": 1}
    if incident:
        body["incident_id"] = incident
    if cost is not None:
        body["score"] = {"cost_usd": cost}
    (run / "manifest.json").write_text(json.dumps(body))


# --- reading the spend ---------------------------------------------------------------------------


def test_manifests_are_selected_by_the_sweep_id_and_nothing_else(tmp_path: Path) -> None:
    """Q60's `sweep.id` is the membership; timestamp arithmetic is what it replaced."""
    _manifest(tmp_path, "20260918T010000Z-a", session="s1", incident="i1", cost=0.5)
    _manifest(tmp_path, "20260918T020000Z-b", session="s2", incident="i2", cost=9.0)
    _manifest(tmp_path, "20260918T030000Z-c", session="s1", incident="i3", cost=0.7)
    _manifest(tmp_path, "20260918T040000Z-d", session=None, incident="i4", cost=9.0)
    (tmp_path / "20260918T050000Z-e").mkdir()  # a run directory with no manifest yet

    found = spend.manifests_of("s1", tmp_path)

    assert [m["run_id"] for m in found] == ["20260918T010000Z-a", "20260918T030000Z-c"]


def test_without_a_database_the_spend_is_the_manifests_sum_and_says_so(tmp_path: Path) -> None:
    _manifest(tmp_path, "r1", session="s1", incident="i1", cost=0.5)
    _manifest(tmp_path, "r2", session="s1", incident="i2", cost=None)  # failed before scoring
    _manifest(tmp_path, "r3", session="s1", incident="i3", cost=0.7)

    result = spend.session_spend("s1", None, root=tmp_path)

    assert result.usd == 1.2 and result.runs == 3
    assert result.source == "manifests"
    assert "from the manifests" in result.render()


def test_with_a_database_the_spend_is_the_store_s_tokens_for_the_sweep_s_incidents(
    tmp_path: Path,
) -> None:
    """**The case the manifests miss.** A run that failed after spending has an incident and a
    trajectory and no `score.cost_usd`; the store has its tokens. Priced at the harness's table."""
    _manifest(tmp_path, "r1", session="s1", incident="i1", cost=0.5)
    _manifest(tmp_path, "r2", session="s1", incident="i2", cost=None)
    _manifest(tmp_path, "other", session="s2", incident="i9", cost=50.0)
    asked: list[tuple[str, Any]] = []

    class Cur:
        def __enter__(self) -> Cur:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def execute(self, sql: str, params: Any) -> None:
            asked.append((sql, params))

        def fetchone(self) -> tuple[int, int]:
            return (1_000_000, 100_000)  # $5 in, $2.50 out

    class Conn:
        rollbacks = 0

        def __enter__(self) -> Conn:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def cursor(self) -> Cur:
            return Cur()

        def rollback(self) -> None:
            Conn.rollbacks += 1

    result = spend.session_spend("s1", "postgresql://x", root=tmp_path, connect=lambda dsn: Conn())

    assert result.usd == 7.5 and result.runs == 2 and result.source == "trajectory store"
    assert asked[0][1] == (["i1", "i2"],), "this sweep's incidents, not s2's"
    assert "trajectory_steps" in asked[0][0] and "incident_id = ANY" in asked[0][0]
    assert Conn.rollbacks == 1, "a read that ends its transaction (pgread)"


def test_the_price_table_is_the_one_the_harness_scores_with() -> None:
    """One table, restated to keep `spend` light. A ceiling in different dollars from the
    figures it protects would be a ceiling on something else."""
    from evalharness import run

    assert (spend.USD_PER_MTOK_IN, spend.USD_PER_MTOK_OUT) == (
        run.USD_PER_MTOK_IN,
        run.USD_PER_MTOK_OUT,
    )


# --- stopping at the ceiling ---------------------------------------------------------------------


def _reader(readings: list[float]) -> Any:
    """A spend reader that returns the next figure each time it is asked."""
    it = iter(readings)
    last = {"v": 0.0}

    def read() -> spend.Spend:
        last["v"] = next(it, last["v"])
        return spend.Spend(usd=last["v"], runs=0, source="trajectory store")

    return read


def test_the_sweep_stops_before_the_launch_that_follows_the_ceiling() -> None:
    """Checked before each launch: at $0.00, $0.60, $1.30 the sweep launches; the read before the
    fourth slot says $2.10 against a $2.00 ceiling and nothing more is launched. The abort names
    the spend, the ceiling, the slot it stopped before and the slots it did not attempt."""
    seen: list[list[str]] = []

    def run(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    result = sweep.sweep(
        ["a", "b", "c", "d", "e"],
        runner=run,
        max_usd=2.0,
        spend=_reader([0.0, 0.6, 1.3, 2.1]),
    )

    assert [argv[1] for argv in seen] == ["a", "b", "c"]
    assert result.aborted is not None and "hard ceiling" in result.aborted
    assert "$2.10" in result.aborted and "$2.00" in result.aborted
    assert "before launching d" in result.aborted
    assert "2 slot(s) were not attempted" in result.aborted
    assert result.exit_code == 1, "a stopped sweep is not a whole catalog"
    rendered = "\n".join(result.render())
    assert "SWEEP ABORTED" in rendered
    assert "spend: $2.10" in rendered and "ceiling $2.00" in rendered


def test_without_a_ceiling_the_sweep_runs_the_catalog_out_and_the_report_says_none() -> None:
    seen: list[list[str]] = []

    def run(argv: list[str]) -> int:
        seen.append(argv)
        return 0

    result = sweep.sweep(["a", "b"], runner=run, spend=_reader([50.0, 60.0, 70.0]))

    assert len(seen) == 2 and result.aborted is None
    assert result.spent is not None and result.spent.usd == 70.0, "read once more at the end"
    assert "ceiling none" in "\n".join(result.render())


def test_a_library_call_without_a_reader_is_unchanged() -> None:
    """Every test that predates Q70 calls `sweep()` this way; a ceiling with no reader would be a
    ceiling on a number nobody read."""
    result = sweep.sweep(["a"], runner=lambda argv: 0, max_usd=0.0)

    assert result.aborted is None and result.spent is None
    assert result.ceiling_usd == 0.0


def test_the_ceiling_is_checked_before_the_settle_wait() -> None:
    """A sweep at its ceiling must not sit five minutes to be told so."""
    waits: list[int] = []

    def run(argv: list[str]) -> int:
        return 0

    sweep.sweep(
        ["a", "b"],
        runner=run,
        settle=300,
        sleeper=waits.append,
        max_usd=1.0,
        spend=_reader([0.0, 1.0]),
    )

    assert waits == [], "stopped before the wait that would have preceded b"


# --- the CLI -------------------------------------------------------------------------------------


def test_the_flag_exists_and_the_ceiling_is_printed_before_the_sweep_starts() -> None:
    import inspect

    args = sweep.parser().parse_args(["--max-usd", "70"])
    assert args.max_usd == 70.0
    assert sweep.parser().parse_args([]).max_usd is None

    source = inspect.getsource(sweep.main)
    assert "ceiling: none" in source, "an omitted ceiling is printed, not inferred"
    assert "session_spend" in source, "read from the store, not estimated"
