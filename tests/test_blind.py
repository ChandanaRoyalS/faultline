"""The blind draw (T4.7).

No world and no injection here: the draw, the seal and the pool arithmetic are the parts that
decide what the timing measures, and they are the parts that can be checked without spending a
world.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

from evalharness import blind


def a_draw(
    scenario_id: str = "cart-redis-misconfig", pool: tuple[str, ...] = ("a", "b")
) -> blind.Draw:
    return blind.Draw(scenario_id=scenario_id, pool=pool, drawn_at="2026-09-05T00:00:00Z")


# --- the pool ------------------------------------------------------------------


def test_a_drawn_scenario_is_not_drawn_again() -> None:
    """**Without replacement.** Drawing with it could time one scenario three times and leave two
    unmeasured, and a median over that is one scenario's difficulty wearing the label of five."""
    assert blind.remaining(["a", "b", "c"], ["b"]) == ["a", "c"]
    assert blind.remaining(["a", "b"], ["a", "b"]) == []


def test_the_draw_comes_from_what_is_left() -> None:
    rng = random.Random(0)
    for _ in range(20):
        assert blind.draw(["a", "b", "c"], ["a", "c"], rng) == "b"


def test_an_exhausted_pool_refuses_rather_than_repeating() -> None:
    with pytest.raises(blind.DrawError) as refusal:
        blind.draw(["a", "b"], ["a", "b"])
    assert "every scenario" in str(refusal.value)
    assert "repeats" in str(refusal.value)


def test_the_draw_is_uniform_over_what_remains() -> None:
    """Not a distributional proof - a check that nothing in the ordering pins the answer. A draw
    that always returned the first remaining id would pass every other test in this file."""
    rng = random.Random(7)
    seen = {blind.draw(["a", "b", "c", "d"], [], rng) for _ in range(200)}
    assert seen == {"a", "b", "c", "d"}


# --- the seal ------------------------------------------------------------------


def test_the_seal_records_the_pool_it_was_drawn_from(tmp_path: Path) -> None:
    """**The prior travels with the attempt.** What a reader needs to judge the contamination is
    the size of the answer set, and it shrinks as the pool is used up."""
    path = tmp_path / "seal.json"
    blind.seal(a_draw(pool=("a", "b", "c", "d", "e")), path)

    held = json.loads(path.read_text())
    assert held["pool"] == ["a", "b", "c", "d", "e"]
    assert blind.unseal(path).prior == "1 in 5"


def test_a_second_draw_refuses_while_one_is_sealed(tmp_path: Path) -> None:
    """Two sealed draws means neither attempt has one fault in it - the same argument the manual
    RCA clock makes about two clocks running at once."""
    path = tmp_path / "seal.json"
    blind.seal(a_draw(), path)

    with pytest.raises(blind.DrawError) as refusal:
        blind.seal(a_draw("ad-memory-squeeze"), path)
    assert "already sealed" in str(refusal.value)


def test_unsealing_an_empty_seal_refuses(tmp_path: Path) -> None:
    with pytest.raises(blind.DrawError):
        blind.unseal(tmp_path / "nothing.json")


def test_the_seal_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "seal.json"
    original = blind.Draw(
        scenario_id="ad-memory-squeeze",
        pool=("ad-memory-squeeze", "cart-redis-misconfig"),
        drawn_at="2026-09-05T00:00:00Z",
        incident_id="abc-123",
    )
    blind.seal(original, path)

    assert blind.unseal(path) == original


def test_the_seal_file_says_not_to_open_it() -> None:
    """**The filename is the instruction.** A file called `current.json` is one nobody thinks
    twice about opening, and the seal is a discipline rather than a control - it is a `cat` away
    on purpose. What makes it worth anything is that the transcript shows what was known when.
    """
    assert "DO-NOT-OPEN" in blind.SEAL.name


# --- what the module deliberately does not do ----------------------------------


def test_the_draw_does_not_score() -> None:
    """Scoring at record time would print right-or-wrong the moment she answered, and the next
    draw would be taken by someone who had just been told how the last one went. Whether an
    answer matched is `manual_rca.Reference.correct`'s job, computed later against the bundle.
    """
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(blind))
    called = {
        ast.unparse(node.func).rsplit(".", 1)[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }

    assert "bundle_for" not in called
    assert "score_label" not in called


def test_the_settle_matches_the_harness_so_the_two_clocks_start_alike() -> None:
    """The responder is handed the same incident the pipeline was handed. A responder timed from
    the first episode would be timed partly on waiting for the blast radius to fill, which the
    pipeline's own latency figure does not include."""
    from evalharness import run

    assert blind.SETTLE_AFTER_ALERT_SECONDS == run.SETTLE_AFTER_ALERT_SECONDS


# --- the driver (T4.7) ---------------------------------------------------------
#
# `blind.py` shipped with the draw, the seal, the pool arithmetic and tests for all three, and
# nothing that ran them. Seventh instance in this project of a thing that was built, green, and
# uninvoked - and it arrived in the commit whose tests assert the module's purity.


def test_the_pool_is_dev_sweep_nines_five() -> None:
    """**Pinned in code, and named in the protocol before the first draw.** A pool chosen per
    invocation is a pool that can be narrowed after a bad attempt, which is the self-timed version
    of re-running a scored run to improve a number."""
    from evalharness import blind_cli

    assert set(blind_cli.POOL) == {
        "ad-memory-squeeze",
        "cart-dependency-latency",
        "cart-redis-misconfig",
        "frauddetection-memory-squeeze",
    }


def test_the_leaked_scenario_cannot_be_drawn() -> None:
    """**`cart-bad-image-tag` was spoiled and is out.** A revert command shelled out without
    capturing stdout, the injector printed the scenario name, and the responder was handed the
    answer to a fault she had not investigated. It cannot be timed as a recognition task now.

    Pinned by a test rather than left to a docstring, because the tempting repair - quietly
    putting it back once the leak is a few weeks old - is exactly the move `POOL`'s own docstring
    forbids, and the person most likely to make it is the one who remembers the reason.
    """
    from evalharness import blind_cli

    assert "cart-bad-image-tag" not in blind_cli.POOL
    assert len(blind_cli.POOL) == 4, "n=4 against T4.7's five, and the reference says so"


def test_the_protocol_names_the_same_five_as_the_code() -> None:
    """Two lists that must agree, so a test holds them together rather than a reviewer."""
    from evalharness import blind_cli

    protocol = (
        Path(__file__).parent.parent / "evals/manual-rca/PROTOCOL-2026-09-05.md"
    ).read_text()
    for scenario_id in blind_cli.POOL:
        assert f"`{scenario_id}`" in protocol, f"{scenario_id} is drawn but not registered"


def test_status_does_not_print_the_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """**`--status` exists so she can check her clock without opening the seal**, and a status
    line that named the draw would *be* the seal."""
    from evalharness import blind_cli

    seal_path = tmp_path / "seal.json"
    blind.seal(
        blind.Draw(
            scenario_id="frauddetection-memory-squeeze",
            pool=("a", "b", "c", "d", "e"),
            drawn_at="2026-09-05T00:00:00+00:00",
            incident_id="inc-1",
            clock_started_at="2026-09-05T00:00:00+00:00",
        ),
        seal_path,
    )

    assert (
        blind_cli.run(["--status", "--seal", str(seal_path), "--ledger", str(tmp_path / "l")]) == 0
    )
    out = capsys.readouterr().out
    assert "inc-1" in out
    assert "1 in 5" in out
    assert "frauddetection" not in out


def test_an_answer_without_a_draw_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from evalharness import blind_cli

    code = blind_cli.run(
        ["--answer", "--fault-class", "x", "--service", "y", "--seal", str(tmp_path / "none.json")]
    )
    assert code == 3
    assert "no draw is open" in capsys.readouterr().out


def test_an_answer_missing_the_service_is_refused_and_the_clock_keeps_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """T4.2 made *which service broke* a scored axis. And the refusal leaves the clock alone:
    discarding the elapsed time would send her back to start a second, shorter investigation of a
    fault she has now seen."""
    from evalharness import blind_cli

    seal_path = tmp_path / "seal.json"
    blind.seal(
        blind.Draw(
            scenario_id="ad-memory-squeeze",
            pool=("a", "b"),
            drawn_at="2026-09-05T00:00:00+00:00",
            clock_started_at="2026-09-05T00:00:00+00:00",
        ),
        seal_path,
    )

    code = blind_cli.run(
        ["--answer", "--fault-class", "resource_exhaustion", "--seal", str(seal_path)]
    )

    assert code == 3
    assert "still running" in capsys.readouterr().out
    assert seal_path.exists(), "the draw must survive a refused answer"


def test_the_attempt_takes_its_scenario_from_the_seal_not_the_operator(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The design's one load-bearing detail.** A flow that asked her to name the scenario when
    recording would require her to know it, undoing the draw at the last step.

    The revert is stubbed: this test is about what gets written, and shelling out to
    `faultline-inject` here would need a world.
    """
    from evalharness import blind_cli
    from evalharness import manual_rca as rca

    monkeypatch.setattr(blind_cli, "_sh", lambda argv: (0, ""))
    seal_path, ledger = tmp_path / "seal.json", tmp_path / "attempts.jsonl"
    blind.seal(
        blind.Draw(
            scenario_id="cart-redis-misconfig",
            pool=("a", "b", "c", "d", "e"),
            drawn_at="2026-09-05T00:00:00+00:00",
            incident_id="inc-9",
            clock_started_at="2026-09-05T00:00:00+00:00",
        ),
        seal_path,
    )

    code = blind_cli.run(
        [
            "--answer",
            "--fault-class",
            "bad_config",
            "--service",
            "cartservice",
            "--seal",
            str(seal_path),
            "--ledger",
            str(ledger),
        ]
    )

    assert code == 0
    written = rca.load(ledger)
    assert [a.scenario_id for a in written] == ["cart-redis-misconfig"]
    assert written[0].elapsed_seconds > 0
    assert "1 in 5" in written[0].notes, "the prior travels with the attempt"
    assert not seal_path.exists(), "the seal is opened once and removed"
    assert "it was   : cart-redis-misconfig" in capsys.readouterr().out


def test_giving_up_is_recorded_rather_than_dropped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An investigation abandoned after twenty minutes is data about difficulty, and dropping it
    would make the median a median over the easy ones."""
    from evalharness import blind_cli
    from evalharness import manual_rca as rca

    monkeypatch.setattr(blind_cli, "_sh", lambda argv: (0, ""))
    seal_path, ledger = tmp_path / "seal.json", tmp_path / "attempts.jsonl"
    blind.seal(
        blind.Draw(
            scenario_id="cart-bad-image-tag",
            pool=("a", "b"),
            drawn_at="2026-09-05T00:00:00+00:00",
            clock_started_at="2026-09-05T00:00:00+00:00",
        ),
        seal_path,
    )

    assert blind_cli.run(["--give-up", "--seal", str(seal_path), "--ledger", str(ledger)]) == 0
    written = rca.load(ledger)
    assert written[0].gave_up is True
    assert written[0].fault_class == ""


def test_abandoning_a_draw_never_prints_the_scenario(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """**The regression that cost the deliverable an n.** The first draw was closed with a script
    typed at the terminal that shelled out to `faultline-inject stop` without capturing stdout, so
    the injector printed the scenario name and the responder was handed an answer she had not
    worked for. A procedure that exists only as a command someone composes under time pressure is
    a procedure with no properties."""
    from evalharness import blind_cli

    calls: list[list[str]] = []
    monkeypatch.setattr(blind_cli, "_sh", lambda argv: (calls.append(argv), (0, ""))[1])
    seal_path = tmp_path / "seal.json"
    blind.seal(
        blind.Draw(
            scenario_id="frauddetection-memory-squeeze",
            pool=("a", "b"),
            drawn_at="2026-09-05T00:00:00+00:00",
            clock_started_at="2026-09-05T00:00:00+00:00",
        ),
        seal_path,
    )

    assert blind_cli.run(["--abandon", "--seal", str(seal_path)]) == 0
    out = capsys.readouterr().out

    assert "frauddetection" not in out, "the scenario must not reach the terminal"
    assert calls == [["faultline-inject", "stop", "frauddetection-memory-squeeze"]]
    assert not seal_path.exists()


def test_abandoning_records_no_attempt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`--give-up` records an abandoned investigation, which is data about difficulty. `--abandon`
    records nothing, because nothing was investigated. Conflating them would put a void into the
    median's denominator."""
    from evalharness import blind_cli
    from evalharness import manual_rca as rca

    monkeypatch.setattr(blind_cli, "_sh", lambda argv: (0, ""))
    seal_path, ledger = tmp_path / "seal.json", tmp_path / "attempts.jsonl"
    blind.seal(
        blind.Draw(
            scenario_id="ad-memory-squeeze",
            pool=("a", "b"),
            drawn_at="2026-09-05T00:00:00+00:00",
            clock_started_at="2026-09-05T00:00:00+00:00",
        ),
        seal_path,
    )

    blind_cli.run(["--abandon", "--seal", str(seal_path), "--ledger", str(ledger)])

    assert rca.load(ledger) == []
