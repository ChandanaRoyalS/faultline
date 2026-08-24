"""Remembering which alert-episode transitions have already been published (T2.1).

The dedupe rule in one line: **the same `(fingerprint, startsAt, status)` seen again is a
repeat notification, not a second transition.** Alertmanager re-sends a firing alert every
`repeat_interval` (1h here) and retries a delivery the receiver failed to accept; neither
is new information, and both would otherwise open a second incident for one alert.

This state has to outlive the process. A receiver restarted between an alert's first
notification and its hourly repeat has no memory of the first, so an in-process dict makes
every restart a source of duplicate incidents - and restarts are exactly what happens
during a deploy, which is when alerts are most likely to be firing. Redis holds it
(ADR-0001 already put Redis in the stack; ADR-0015 records the reasoning).
"""

from __future__ import annotations

from typing import Protocol

import redis


class EpisodeLog(Protocol):
    """What the receiver needs from dedupe state, and the seam the tests substitute at."""

    def first_sight(self, key: str) -> bool:
        """Record `key` and report whether it had not been seen before.

        Must be atomic: two deliveries of the same repeat arriving together may not both
        be told they are first.
        """


class RedisEpisodeLog:
    """`SET key NX EX ttl` - one round trip, atomic by construction.

    The TTL bounds the key space without any sweeping. It must comfortably exceed the
    longest episode we expect to see, because an expiry while an alert is still firing
    makes the next repeat notification look new. Seven days against a 1h `repeat_interval`
    is a wide margin; an alert firing for a week is a problem of its own.
    """

    def __init__(self, client: redis.Redis, prefix: str, ttl_seconds: int) -> None:
        self._client = client
        self._prefix = prefix
        self._ttl = ttl_seconds

    def first_sight(self, key: str) -> bool:
        stored = self._client.set(f"{self._prefix}{key}", "1", nx=True, ex=self._ttl)
        return bool(stored)


class InMemoryEpisodeLog:
    """Dedupe state in a set. **For tests, and for nothing else.**

    It is the same rule with the durability removed, which is the one property that
    matters in production - see this module's docstring.
    """

    def __init__(self) -> None:
        self.seen: set[str] = set()

    def first_sight(self, key: str) -> bool:
        if key in self.seen:
            return False
        self.seen.add(key)
        return True
