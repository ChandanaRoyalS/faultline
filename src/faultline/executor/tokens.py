"""The approval token: single-use, action-bound, and worth nothing to anyone who cannot sign.

**"Approve this rollback, not 'approve'."** The proposal's own words for the safety property, and
the reason every claim that identifies *what* is being approved is inside the signed payload: the
incident, the proposal, the action id, the canonical target and the catalog version it was granted
against (ADR-0032: *"pin it per approval so an approval token cannot outlive the catalog it was
granted against"*). Change any one and the signature no longer verifies; present it against a
different incident and the executor sees a token for somebody else's incident.

**Single use is the audit's job, not the token's.** A token cannot know whether it has been
presented before; the append-only `action_audit` can (`audit.AuditStore.spent`). The two halves
are deliberately in different places, so that forging a token requires the key *and* editing a
table that refuses edits.

The format is a plain `base64url(json).base64url(hmac)` - no library, no algorithm negotiation,
nothing a client can choose. HMAC-SHA256 over the exact payload bytes, compared in constant time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


class TokenError(ValueError):
    """The token is not one this executor will act on. The message says why, and is safe to
    record: it never contains the token or the key."""


@dataclass(frozen=True, slots=True)
class Claims:
    """What an approval says. Every field is part of the signature."""

    token_id: str
    incident_id: str
    proposal_id: str
    """The trajectory id and step seq of the proposal (`<trajectory>#<seq>`), or for an
    operator-supplied proposal the run directory it was taken from. Named so the audit can point
    at the exact object a human read before approving."""

    action_id: str
    target: str
    """Canonical - the compose service name (`injector.world.canonical_service`)."""

    catalog_version: int
    confirm_within_seconds: int
    issued_at: str
    expires_at: str

    def expired(self, now: datetime) -> bool:
        return now >= datetime.fromisoformat(self.expires_at)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _sign(payload: bytes, key: str) -> bytes:
    return hmac.new(key.encode("utf-8"), payload, hashlib.sha256).digest()


def _require_key(key: str) -> None:
    if not key:
        raise TokenError(
            "no token key is configured (FAULTLINE_EXECUTOR_TOKEN_KEY). Refusing to sign or "
            "verify with an empty key: a token anyone can forge guards nothing."
        )


def mint(
    *,
    incident_id: str,
    proposal_id: str,
    action_id: str,
    target: str,
    catalog_version: int,
    confirm_within_seconds: int,
    key: str,
    ttl_seconds: int,
    now: datetime | None = None,
) -> tuple[str, Claims]:
    """Issue a token for exactly this action against exactly this target. Returns the token
    string and the claims it carries, so the caller can record the id without the token."""
    _require_key(key)
    moment = now or datetime.now(UTC)
    claims = Claims(
        token_id=secrets.token_hex(8),
        incident_id=incident_id,
        proposal_id=proposal_id,
        action_id=action_id,
        target=target,
        catalog_version=catalog_version,
        confirm_within_seconds=confirm_within_seconds,
        issued_at=moment.isoformat(),
        expires_at=(moment + timedelta(seconds=ttl_seconds)).isoformat(),
    )
    payload = json.dumps(asdict(claims), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{_b64(payload)}.{_b64(_sign(payload, key))}", claims


def verify(token: str, *, key: str, now: datetime | None = None) -> Claims:
    """The claims, if and only if the signature holds and the token has not expired.

    Order: shape, signature, then expiry - so a forged token is refused as forged even when its
    forger also got the date wrong, and the message never leaks which claim was off."""
    _require_key(key)
    try:
        payload_text, signature_text = token.strip().split(".", 1)
        payload = _unb64(payload_text)
        signature = _unb64(signature_text)
    except (ValueError, TypeError) as exc:
        raise TokenError("token is not in the form <payload>.<signature>") from exc
    if not hmac.compare_digest(signature, _sign(payload, key)):
        raise TokenError("token signature does not verify under this executor's key")
    try:
        raw: dict[str, Any] = json.loads(payload)
        claims = Claims(**raw)
    except (ValueError, TypeError) as exc:
        raise TokenError("token payload is not a claims object") from exc
    if claims.expired(now or datetime.now(UTC)):
        raise TokenError(f"token {claims.token_id} expired at {claims.expires_at}")
    return claims
