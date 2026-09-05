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
