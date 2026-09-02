"""Ranking change candidates by time-proximity and blast radius (T3.4).

The plan's T3.4 asks for changes *"ranked by suspicion"*, by *"time-proximity plus blast-radius
ranking of candidate changes"*, delivered as *"ranked suspicious-change evidence per incident"*.
Until this module the change tool returned records oldest first and left the ranking to whatever
the specialist made of the timestamps. The ranking now happens in the tool, from two inputs the
agent layer already had and no model chose: alert onset, and triage's blast radius.

**An ordering, not a probability.** Nothing here is a calibrated score, and no decay constant
was fitted to anything, because there is nothing to fit it to - the recorded corpus has one
injected change per scenario. The rank is a lexicographic sort with each key stated:

1. **Causal tier.** A change *before* onset could have caused it; a change *after* onset cannot
   have caused the onset and ranks below every change that could. It is still shown - a revert
   after onset is how a responder learns someone already tried something.
2. **Blast-radius tier**, from triage's `Direction`: `candidate_cause` (a callee of an alerting
   service - the place the error might have come from) ranks above `seed` (the alerting service
   itself), which ranks above `also_affected` (a caller reached by propagation - affected by the
   failure, on the measured direction of propagation, rather than the origin of it). A service
   outside the radius ranks last.
3. **Hops** from the nearest alerting service, fewer first.
4. **Lead**: distance from onset, closer first.

One dispatch queries one service (T3.4c), so within a single result the radius tier is constant
and the order is causal tier then lead. The tier and hops are still written onto the result,
because the same rule is applied to every change dispatch of an investigation against the same
onset and the same radius - so two results the synthesizer holds side by side are ranked on one
scale, which is what makes the evidence *per incident* rather than per service.

**What this does not move.** `TOOL_BEHAVIOUR_REVISION` is not bumped: the set of records a
call returns is unchanged, and every annotation is derived from the record's own timestamp and
from triage output the responder already held. The decision is recorded in ADR-0019's T3.4
addendum rather than assumed.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from faultline.tools.changes import ChangeRecord

CAUSAL_TIERS: dict[str, int] = {"before_onset": 0, "after_onset": 1}
RADIUS_TIERS: dict[str, int] = {
    "candidate_cause": 0,
    "seed": 1,
    "also_affected": 2,
    "outside_radius": 3,
}
OUTSIDE = "outside_radius"


@dataclass(frozen=True, slots=True)
class RadiusStanding:
    """Where one service sits in triage's blast radius, as the ranking sees it."""

    direction: str
    """A triage `Direction` value, or `outside_radius`."""

    hops: int | None
    reason: str | None
    """Triage's `EntryReason` - kept so the result can say a standing rests on an unmeasured
    edge, the way every use of the radius is meant to quote its unmeasured edges."""

    def as_row(self) -> dict[str, Any]:
        return {"direction": self.direction, "hops": self.hops, "reason": self.reason}


OUTSIDE_STANDING = RadiusStanding(direction=OUTSIDE, hops=None, reason=None)


@dataclass(frozen=True, slots=True)
class RankingContext:
    """What the change tool needs to rank: onset, and the radius keyed by canonical service."""

    anchor: datetime
    radius: Mapping[str, RadiusStanding]

    def standing_for(self, service: str) -> RadiusStanding:
        return self.radius.get(service, OUTSIDE_STANDING)


def lead_seconds(at: datetime, anchor: datetime) -> int:
    """Seconds from the change to onset. Positive means the change came first."""
    return int((anchor - at).total_seconds())


def causal_tier(lead: int) -> str:
    return "before_onset" if lead >= 0 else "after_onset"


def rank_key(lead: int, standing: RadiusStanding) -> tuple[int, int, int, int]:
    """The whole ordering rule, in one place, so a test can read it back."""
    return (
        CAUSAL_TIERS[causal_tier(lead)],
        RADIUS_TIERS.get(standing.direction, RADIUS_TIERS[OUTSIDE]),
        standing.hops if standing.hops is not None else 10**6,
        abs(lead),
    )


def rank_changes(
    records: Iterable[ChangeRecord], context: RankingContext, service: str
) -> list[dict[str, Any]]:
    """Rows in rank order, each carrying its rank, lead and causal tier beside `as_row()`."""
    standing = context.standing_for(service)
    scored = sorted(
        ((lead_seconds(record.at, context.anchor), record) for record in records),
        key=lambda pair: (rank_key(pair[0], standing), pair[1].at),
    )
    rows: list[dict[str, Any]] = []
    for position, (lead, record) in enumerate(scored, start=1):
        rows.append(
            {
                **record.as_row(),
                "rank": position,
                "lead_seconds": lead,
                "causal": causal_tier(lead),
            }
        )
    return rows
