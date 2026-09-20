"""The credential lock-out (T6.8), against a clock the test owns.

`tests/test_api_app.py` drives the limiter through the routes; this file drives the object, because
the only property that cannot be tested through a route in reasonable time is the one about time:
that a lock-out ends `window` after the failure that tripped it, and not later because the client
kept knocking.
"""

from __future__ import annotations

from faultline.api import auth


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def limiter(clock: Clock) -> auth.FailureLimiter:
    return auth.FailureLimiter(limit=3, window_seconds=60.0, clock=clock)


def test_the_limit_minus_one_is_not_a_lock_out() -> None:
    clock = Clock()
    fl = limiter(clock)
    fl.record_failure("a")
    fl.record_failure("a")

    assert not fl.blocked("a")
    assert fl.lockouts == 0


def test_the_limit_is_a_lock_out_and_is_counted_once() -> None:
    clock = Clock()
    fl = limiter(clock)
    assert [fl.record_failure("a") for _ in range(3)] == [False, False, True]

    assert fl.blocked("a")
    assert fl.lockouts == 1


def test_the_lock_out_ends_a_window_after_the_failure_that_tripped_it() -> None:
    """A blocked request records nothing, so a client that keeps hammering during the lock-out is
    not locked out forever - the point is to slow a guess, not to be a denial of service against
    whoever shares the address."""
    clock = Clock()
    fl = limiter(clock)
    for _ in range(3):
        fl.record_failure("a")
    clock.now += 59
    assert fl.blocked("a")
    clock.now += 2
    assert not fl.blocked("a")


def test_failures_outside_the_window_do_not_count() -> None:
    clock = Clock()
    fl = limiter(clock)
    fl.record_failure("a")
    fl.record_failure("a")
    clock.now += 61
    fl.record_failure("a")

    assert not fl.blocked("a")


def test_clients_are_independent() -> None:
    clock = Clock()
    fl = limiter(clock)
    for _ in range(3):
        fl.record_failure("a")

    assert fl.blocked("a")
    assert not fl.blocked("b")


def test_the_table_is_bounded() -> None:
    """A flood of addresses evicts the oldest rather than growing the process."""
    clock = Clock()
    fl = auth.FailureLimiter(limit=3, window_seconds=60.0, clock=clock, capacity=2)
    for _ in range(3):
        fl.record_failure("a")
    fl.record_failure("b")
    fl.record_failure("c")

    assert not fl.blocked("a"), "evicted: the table remembers two clients and a is the oldest"


def test_success_does_not_clear_the_count() -> None:
    """There is no success hook at all: a correct password after two wrong ones is still two wrong
    ones, because the alternative lets a guesser reset the counter by knowing the answer."""
    assert not hasattr(auth.FailureLimiter, "record_success")


class FakeRequest:
    def __init__(self, headers: dict[str, str], peer: str | None = "10.0.0.1") -> None:
        self.headers = headers
        self.client = type("Peer", (), {"host": peer})() if peer else None


def test_the_client_is_the_rightmost_forwarded_address() -> None:
    """Caddy appends the peer it saw; anything to the left is what the client chose to send."""
    request = FakeRequest({"x-forwarded-for": "1.1.1.1, 2.2.2.2"})

    assert auth.client_of(request) == "2.2.2.2"  # type: ignore[arg-type]


def test_the_client_is_the_peer_without_a_forwarded_header() -> None:
    assert auth.client_of(FakeRequest({})) == "10.0.0.1"  # type: ignore[arg-type]
    assert auth.client_of(FakeRequest({}, peer=None)) == "unknown"  # type: ignore[arg-type]


def test_the_basic_header_parser_accepts_only_a_well_formed_pair() -> None:
    import base64

    good = base64.b64encode(b"user:pa:ss").decode()
    assert auth.basic_header(FakeRequest({"authorization": f"Basic {good}"})) == (  # type: ignore[arg-type]
        "user",
        "pa:ss",
    )
    no_colon = "Basic " + base64.b64encode(b"nocolon").decode()
    for bad in ("", "Bearer x", "Basic", "Basic !!!", no_colon):
        request = FakeRequest({"authorization": bad})
        assert auth.basic_header(request) is None, bad  # type: ignore[arg-type]
